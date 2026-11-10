"""Non-blocking Home Assistant REST client that never stalls the frame loop.

CircuitPython has no threads and adafruit_requests blocks, so this is a small
HTTP state machine. ``poll(now)`` runs once per frame and does at most one
bounded step (one connect attempt, one send, or one ~1 KB recv):

    IDLE -> CONNECTING -> SENDING -> RECEIVING -> PARSE -> next entity

Each cycle fetches every entity in turn with ``GET /api/states/<entity_id>``
and then waits until the next interval. A request that takes longer than
REQUEST_TIMEOUT_S is closed and counts as a failure; after a failure the
client backs off for max(interval, FAILURE_BACKOFF_S).

``pool`` is anything with getaddrinfo() and socket(): socketpool.SocketPool
on hardware, the CPython ``socket`` module on the desktop.

Interface (shared with home.fake_sensors.FakeSensors):
    poll(now)      call once per frame
    values         {key: (state, unit, t)}
    last_ok        time of the last successful read, or None
    changed        set True when a value changes; the consumer clears it
    interval_s     seconds between reads
    last_error     short description of the latest failure, or None
"""

import errno
import json

REQUEST_TIMEOUT_S = 5.0
FAILURE_BACKOFF_S = 10.0
RESOLVE_RETRY_S = 60.0  # getaddrinfo blocks, so retry a failed lookup rarely
RECV_CHUNK = 1024
BUFFER_SIZE = 4096

IDLE, CONNECTING, SENDING, RECEIVING, PARSE = range(5)


def _errnos(names, fallback):
    found = set(fallback)
    for name in names:
        value = getattr(errno, name, None)
        if value is not None:
            found.add(value)
    return found


# "Try again next frame". Numbers cover Linux (11/114/115) and lwIP on
# CircuitPython (11/119/120), in case the errno module lacks a name.
_WOULD_BLOCK = _errnos(
    ("EAGAIN", "EWOULDBLOCK", "EINPROGRESS", "EALREADY"), (11, 114, 115, 119, 120)
)
# connect() on an already-connected socket: the non-blocking connect finished
_IS_CONN = _errnos(("EISCONN",), (106, 127))
# CircuitPython's connect() with timeout 0 waits 0 s for the handshake and
# raises ETIMEDOUT while it is still in progress (Linux 110, ESP-IDF 116).
# Only the connect step treats this as "not yet"; REQUEST_TIMEOUT_S bounds it.
_CONNECT_PENDING = _WOULD_BLOCK | _errnos(("ETIMEDOUT",), (110, 116))


def _errno_of(exc):
    if getattr(exc, "errno", None) is not None:
        return exc.errno
    return exc.args[0] if exc.args else None


def parse_url(url):
    """'http://host:8123/' -> ('host', 8123). Only plain http is supported."""
    prefix = "http://"
    if not url.startswith(prefix):
        raise ValueError("HA_URL must start with http:// (got %r)" % url)
    hostport = url[len(prefix):].split("/", 1)[0]
    if ":" in hostport:
        host, port = hostport.rsplit(":", 1)
        return host, int(port)
    return hostport, 80


# (key, settings name) for the sensor readout
READOUT_ENTITIES = (
    ("co2", "HA_CO2_ENTITY"),
    ("temperature", "HA_TEMPERATURE_ENTITY"),
    ("humidity", "HA_HUMIDITY_ENTITY"),
)


def from_settings(pool, settings, interval_s, now, connect_timeout=0):
    """Build an HAClient from settings.toml values, or None when HA_URL is unset.
    Raises ValueError for an HA_URL it can't use."""
    url = settings.get("HA_URL")
    if not url:
        return None
    host, port = parse_url(url)
    entities = []
    for key, name in READOUT_ENTITIES:
        entity_id = settings.get(name)
        if entity_id:
            entities.append((key, entity_id))
    return HAClient(
        pool,
        host,
        port,
        settings.get("HA_TOKEN", ""),
        entities,
        interval_s,
        now,
        connect_timeout,
    )


class HAClient:
    def __init__(
        self, pool, host, port, token, entities, interval_s, now=0.0, connect_timeout=0
    ):
        """connect_timeout > 0 makes the first connect() block for up to that
        many seconds instead of being non-blocking: a fallback for a socket
        stack whose non-blocking connect never completes. A bounded stall, once
        per request."""
        self.interval_s = interval_s
        self._connect_timeout = connect_timeout
        self.values = {}
        self.last_ok = None
        self.changed = False
        self.last_error = None

        self._pool = pool
        self._host = host
        self._port = port
        self._entities = list(entities)
        # Requests are built once; only the entity changes between them
        auth = "Bearer " + token
        self._requests = [
            (
                "GET /api/states/%s HTTP/1.0\r\n"  # 1.0: no chunked replies
                "Host: %s:%d\r\n"
                "Authorization: %s\r\n"
                "Accept: application/json\r\n"
                "Connection: close\r\n\r\n" % (entity_id, host, port, auth)
            ).encode()
            for _, entity_id in self._entities
        ]
        self._buf = bytearray(BUFFER_SIZE)
        self._view = memoryview(self._buf)

        self._state = IDLE
        self._sock = None
        self._entity = 0  # index into _entities for the current request
        self._sent = 0
        self._received = 0
        self._deadline = 0.0
        self._next_t = now  # first cycle starts right away
        self._addr = None
        self._failing = False
        self._resolve(now)

    # ------------------------------------------------------------ helpers
    def _resolve(self, now):
        """Look up the host once. Blocking, so only at startup and on a slow retry."""
        try:
            info = self._pool.getaddrinfo(
                self._host, self._port, self._pool.AF_INET, self._pool.SOCK_STREAM
            )
            self._addr = info[0][4]
        except OSError as e:
            self._addr = None
            self._error("resolve %s: %s" % (self._host, e))
            self._failing = True
            self._next_t = now + max(self.interval_s, RESOLVE_RETRY_S)

    def _error(self, message):
        if message != self.last_error:
            print("HA:", message)
        self.last_error = message

    def _close(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def _fail(self, now, message):
        """Abort the cycle; the next one starts after the backoff."""
        self._close()
        self._error(message)
        self._failing = True
        self._state = IDLE
        self._entity = 0
        self._next_t = now + max(self.interval_s, FAILURE_BACKOFF_S)

    def _finish_request(self):
        """Move on to the next entity, or end the cycle."""
        self._close()
        self._state = IDLE
        self._entity += 1
        if self._entity >= len(self._entities):
            self._entity = 0
            # _next_t was set when the cycle started

    # ------------------------------------------------------------ main step
    def poll(self, now):
        if not self._entities:
            return
        state = self._state
        if state == IDLE:
            if self._entity == 0:
                if now < self._next_t:
                    return
                if self._addr is None:
                    self._resolve(now)
                    if self._addr is None:
                        return
                self._next_t = now + self.interval_s
            self._start(now)
            return
        if now > self._deadline:
            self._fail(now, "timeout (%s)" % self._entities[self._entity][1])
            return
        try:
            if state == CONNECTING:
                self._step_connect()
            elif state == SENDING:
                self._step_send()
            elif state == RECEIVING:
                self._step_recv()
            elif state == PARSE:
                self._step_parse(now)
        except OSError as e:
            if _errno_of(e) in _WOULD_BLOCK:
                return  # try again next frame
            self._fail(now, "%s: %s" % (self._entities[self._entity][1], e))

    def _start(self, now):
        try:
            sock = self._pool.socket(self._pool.AF_INET, self._pool.SOCK_STREAM)
        except OSError as e:
            self._fail(now, "socket: %s" % e)
            return
        sock.settimeout(self._connect_timeout)
        self._sock = sock
        self._sent = 0
        self._received = 0
        self._deadline = now + REQUEST_TIMEOUT_S
        self._state = CONNECTING
        self.poll(now)  # the first connect() is part of the same step

    def _step_connect(self):
        # Non-blocking connect: the first call raises EINPROGRESS, later calls
        # raise EALREADY until it completes, then EISCONN (or the real error,
        # e.g. ECONNREFUSED). A call that returns normally also means connected.
        sock = self._sock
        try:
            sock.connect(self._addr)
        except OSError as e:
            code = _errno_of(e)
            if code in _CONNECT_PENDING and not self._connect_timeout:
                return  # still connecting, try again next frame
            if code not in _IS_CONN:
                raise
        if self._connect_timeout:
            sock.settimeout(0)
        self._state = SENDING

    def _step_send(self):
        request = self._requests[self._entity]
        n = self._sock.send(request[self._sent:])
        self._sent += n
        if self._sent >= len(request):
            self._state = RECEIVING

    def _step_recv(self):
        start = self._received
        if start >= BUFFER_SIZE:
            raise OSError("response over %d bytes" % BUFFER_SIZE)
        end = min(start + RECV_CHUNK, BUFFER_SIZE)
        n = self._sock.recv_into(self._view[start:end], end - start)
        if n == 0:  # server closed: the whole response is in the buffer
            self._state = PARSE
        else:
            self._received += n

    def _step_parse(self, now):
        key, entity_id = self._entities[self._entity]
        data = self._buf[: self._received]
        split = data.find(b"\r\n\r\n")
        if split < 0:
            self._fail(now, "%s: incomplete response" % entity_id)
            return
        status_line = bytes(data[: data.find(b"\r\n")])
        parts = status_line.split(b" ")
        status = parts[1].decode() if len(parts) > 1 else "?"
        if status in ("401", "403"):
            # Bad token: every entity would fail the same way
            self._fail(now, "HTTP %s, check HA_TOKEN" % status)
            return
        if status != "200":
            # HA answered, so this isn't an outage: show "--" for this entity
            # (e.g. 404 for a wrong entity ID) and carry on with the cycle.
            self._error("%s: HTTP %s" % (entity_id, status))
            self._set(key, None)
            self._finish_request()
            return
        try:
            body = json.loads(bytes(data[split + 4 :]).decode())
            value = (
                str(body.get("state")),
                body.get("attributes", {}).get("unit_of_measurement"),
                now,
            )
        except (ValueError, AttributeError) as e:
            self._fail(now, "%s: bad JSON: %s" % (entity_id, e))
            return
        self.last_ok = now
        if self._failing:
            print("HA: reading again")
            self._failing = False
            self.last_error = None
        self._set(key, value)
        self._finish_request()

    def _set(self, key, value):
        old = self.values.get(key)
        if value is None:
            if key in self.values:
                del self.values[key]
                self.changed = True
            return
        if old is None or old[0] != value[0] or old[1] != value[1]:
            self.changed = True
        self.values[key] = value
