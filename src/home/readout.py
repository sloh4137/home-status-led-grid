"""Format sensor values (from FakeSensors or HAClient) as panel text lines."""

UNAVAILABLE = "--"
OFFLINE_INTERVALS = 3  # show HA OFFLINE after this many intervals with no success

# (key, label, format); format=None shows the state as-is
LINES = (
    ("co2", "CO2", "%.0f"),
    ("temperature", "T", "%.1f"),
    ("humidity", "H", "%.0f"),
)


def format_value(entry, fmt):
    """entry is (state, unit, t) or None. Returns e.g. '21.4°C' or '--'."""
    if entry is None:
        return UNAVAILABLE
    state, unit, _ = entry
    if fmt is None:
        text = state
    else:
        try:
            text = fmt % float(state)
        except (TypeError, ValueError):  # "unavailable", "unknown", None
            return UNAVAILABLE
    return text + (unit or "").upper()


def is_offline(sensors, now, started):
    """True when there has been no successful read for OFFLINE_INTERVALS
    intervals. started stands in for last_ok before the first success."""
    last = sensors.last_ok if sensors.last_ok is not None else started
    return now - last > OFFLINE_INTERVALS * sensors.interval_s


def sensor_lines(values, offline=False):
    """Panel lines, top to bottom. Offline shows only HA OFFLINE (on the bottom
    line) rather than stale values."""
    if offline:
        return ["", "", "HA OFFLINE"]
    return [
        label + " " + format_value(values.get(key), fmt)
        for key, label, fmt in LINES
    ]
