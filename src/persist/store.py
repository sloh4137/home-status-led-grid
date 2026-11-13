"""Throttled saving of the state document, and where it is saved.

    store = Store(NvmBackend(microcontroller.nvm), persist_seconds(settings), now,
                  import_path="/state.json")
    doc = store.load()                       # parsed document (import applied), or None
    store.provide("settings", app.settings)  # called at save time for that section
    store.mark_dirty()                       # after any change worth keeping
    store.tick(now)                          # once per frame; saves at most once per interval
    store.dump()                             # print the document between marker lines

Callers only set the dirty flag and never block on flash. ``tick`` builds the
document from the providers and writes it when dirty and at least
``interval_s`` has passed since the last save (or since startup). A change
made less than ``interval_s`` before a power loss is lost.

Backends have ``read() -> text or None``, ``write(text)`` and ``pretty``:

- NvmBackend: microcontroller.nvm on the board (see the nvm notes below).
- FileBackend: a JSON file on the desktop, written to PATH.tmp then renamed.

Import (board only, ``import_path``): ``load`` also reads CIRCUITPY/state.json
if it exists. A file whose checksum equals the backend's ``import_crc`` was
already imported and is ignored, so it can stay on the drive. Otherwise it is
parsed like any load and replaces the saved document per section
(document.merge), and the store is marked dirty so the next save records the
new ``import_crc`` together with the imported state. A broken file keeps the
saved state, isn't recorded (so a fixed file is picked up next time) and sets
``notice`` for the status line. The board never deletes or rewrites the file:
code can't write to CIRCUITPY while the PC can.
"""

import struct
import time

from persist import document

try:
    from binascii import crc32 as _crc32
except ImportError:
    _crc32 = None


DUMP_BEGIN = "---STATE BEGIN---"
DUMP_END = "---STATE END---"
BAD_IMPORT = "BAD STATE.JSON"


class Store:
    def __init__(self, backend, interval_s, now, import_path=None):
        self.backend = backend
        self.interval_s = interval_s
        self.import_path = import_path
        self.dirty = False
        # A short message for the status line after load (BAD STATE.JSON), or None
        self.notice = None
        self._last_save = now
        self._sections = {}

    def load(self):
        try:
            text = self.backend.read()
        except (OSError, RuntimeError) as e:
            # e.g. "NVS Error": boot with defaults rather than not at all
            print("state: load failed (%s)" % e)
            text = None
        doc = document.parse(text)
        if self.import_path:
            doc = self._import(doc)
        return doc

    def _import(self, doc):
        path = self.import_path
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            return doc  # no file to import
        crc = checksum(data)
        backend = self.backend
        if crc == getattr(backend, "import_crc", None):
            print("state: %s already imported" % path)
            return doc
        try:
            text = data.decode()
        except UnicodeError:
            print("state: not UTF-8 text")
            text = None
        imported = document.parse(text)
        if imported is None:
            print("state: %s not imported; keeping the saved state" % path)
            self.notice = BAD_IMPORT
            return doc
        print("state: imported %s" % path)
        backend.import_crc = crc
        self.dirty = True
        return document.merge(doc, imported)

    def provide(self, name, section):
        """Register ``section()``, which returns the dict saved under ``name``."""
        self._sections[name] = section

    def mark_dirty(self):
        self.dirty = True

    def tick(self, now):
        if self.dirty and now - self._last_save >= self.interval_s:
            self.save(now)

    def flush(self, now):
        """Save now if anything is unsaved (e.g. when the simulator closes)."""
        if self.dirty:
            self.save(now)

    def build_document(self):
        """The current document, built from the providers."""
        return document.build({name: f() for name, f in self._sections.items()})

    def dump(self):
        """Print the current document, pretty, between marker lines on the
        console (tools/pull_state.py looks for them)."""
        print(DUMP_BEGIN)
        print(document.dumps(self.build_document(), pretty=True), end="")
        print(DUMP_END)

    def save(self, now):
        # Even a failed write waits a full interval before the next try
        self._last_save = now
        t = time.monotonic_ns()
        doc = self.build_document()
        text = document.dumps(doc, self.backend.pretty)
        try:
            self.backend.write(text)
        except (OSError, RuntimeError, ValueError) as e:
            print("state: save failed (%s)" % e)
            return
        self.dirty = False
        print(
            "state: saved %d bytes in %.1f ms"
            % (len(text), (time.monotonic_ns() - t) / 1e6)
        )


# ---------------------------------------------------------------- nvm
# Findings from ports/espressif/common-hal/nvm/ByteArray.c (CircuitPython 10.x):
# - len(microcontroller.nvm) is CIRCUITPY_INTERNAL_NVM_SIZE, 8 KB, stored as
#   one NVS blob in the 20 KB "nvs" partition (5 pages of 4 KB).
# - Every slice write reads the whole blob, calls nvs_erase_all(), then
#   writes the full 8 KB blob back and commits. Every slice read also fetches
#   the whole blob. So: one slice assignment per save, and few reads.
# - The old blob is erased *before* the new one is written, so A/B slots
#   inside nvm can't help. A power loss during a save leaves either the old
#   record, the new one, or no blob at all (reads as zeros -> bad magic ->
#   defaults). It never leaves a mixed record that passes the CRC.
# - Wear: each save writes ~8 KB of NVS entries, so roughly 2 page erases
#   spread over 5 pages. At the 60 s maximum that's ~1440 saves/day ->
#   ~580 erases per page per day (~170 days to 100k cycles), but saves only
#   happen when something changed, so a few saves a day costs nothing.
#   Keep dirty events rare (menu changes, births/deaths, hourly ages).
#
# Record: magic "LPND" | version u8 | import_crc u32 | length u16 | crc u32 | JSON
MAGIC = b"LPND"
RECORD_VERSION = 1
HEADER = "<4sBIHI"
HEADER_SIZE = struct.calcsize(HEADER)


def checksum(data):
    """CRC-32 when the build has binascii.crc32, otherwise Adler-32."""
    if _crc32 is not None:
        return _crc32(data) & 0xFFFFFFFF
    a, b = 1, 0
    for byte in data:
        a = (a + byte) % 65521
        b = (b + a) % 65521
    return (b << 16) | a


class NvmBackend:
    pretty = False

    def __init__(self, nvm):
        self.nvm = nvm
        # Checksum of the last imported CIRCUITPY/state.json (0 = none)
        self.import_crc = 0

    def read(self):
        nvm = self.nvm
        magic, version, import_crc, length, crc = struct.unpack(
            HEADER, bytes(nvm[0:HEADER_SIZE])
        )
        if magic != MAGIC:
            print("state: no saved state in nvm")
            return None
        if version != RECORD_VERSION:
            print("state: unknown nvm record version %d" % version)
            return None
        if HEADER_SIZE + length > len(nvm):
            print("state: bad nvm record length %d" % length)
            return None
        data = bytes(nvm[HEADER_SIZE : HEADER_SIZE + length])
        if checksum(data) != crc:
            print("state: nvm checksum mismatch")
            return None
        self.import_crc = import_crc
        return data.decode()

    def write(self, text):
        data = text.encode()
        if HEADER_SIZE + len(data) > len(self.nvm):
            raise ValueError(
                "%d bytes don't fit in %d bytes of nvm" % (len(data), len(self.nvm))
            )
        record = (
            struct.pack(
                HEADER, MAGIC, RECORD_VERSION, self.import_crc, len(data), checksum(data)
            )
            + data
        )
        # One slice assignment = one NVS blob rewrite (see above)
        self.nvm[0 : len(record)] = record


# ---------------------------------------------------------------- file
class FileBackend:
    """Desktop: the file *is* the save. Pretty-printed so it's easy to edit;
    edit it while the simulator is stopped, or its next save overwrites it."""

    pretty = True

    def __init__(self, path):
        self.path = path

    def read(self):
        try:
            with open(self.path) as f:
                return f.read()
        except OSError:
            # Missing file: a fresh start, not worth a message
            return None

    def write(self, text):
        import os

        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            f.write(text)
        os.replace(tmp, self.path)
