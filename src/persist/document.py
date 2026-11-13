"""The saved JSON document and its validation.

    {
      "v": 1,
      "settings": {"rotation": 90, "sensors_on": true},
      "pond": {"next_id": 7, "fish": [{"id": 3, "species": "koi", ...}]}
    }

Each section has an owner: App owns ``settings`` (validated here) and the
pond scene owns ``pond`` (validated by creatures/genome.py).
Loading puts the defaults first, then overlays each known field that is
valid, so old saves keep working when fields are added. Unknown keys and
invalid values are dropped, with the reason printed on the serial console.
An unparseable document means defaults.

An imported file (CIRCUITPY/state.json) replaces the saved document per
section: see ``merge``.
"""

import json

VERSION = 1

# Top-level sections, each replaced as a whole by an import
SECTIONS = ("settings", "pond")

# Pretty dumps write known keys in this order, then any others.
# MicroPython dicts don't keep insertion order, so without it the board's dump
# would list each fish's keys in hash order.
KEY_ORDER = (
    "v", "settings", "pond",
    "rotation", "sensors_on",
    "next_id", "fish",
    "id", "species", "variety", "seed", "max_size", "age_hours", "offspring",
)

ROTATIONS = (0, 90, 180, 270)
DEFAULT_SETTINGS = {"rotation": 0, "sensors_on": True}


def _drop(section, key, value, reason):
    print("state: dropped %s.%s = %r (%s)" % (section, key, value, reason))


def parse(text):
    """JSON text -> document dict, or None if it isn't a usable document."""
    if text is None:
        return None
    try:
        doc = json.loads(text)
    except ValueError as e:
        print("state: unparseable JSON (%s)" % e)
        return None
    if not isinstance(doc, dict):
        print("state: not a JSON object")
        return None
    v = doc.get("v", VERSION)
    if v != VERSION:
        print("state: unknown version %r" % (v,))
        return None
    return doc


def settings_from(doc):
    """The validated ``settings`` section of a document (or of None)."""
    settings = dict(DEFAULT_SETTINGS)
    saved = doc.get("settings") if doc else None
    if saved is None:
        return settings
    if not isinstance(saved, dict):
        _drop("state", "settings", saved, "not an object")
        return settings
    for key, value in saved.items():
        if key == "rotation":
            # bool is an int subclass, so rule it out explicitly
            if isinstance(value, int) and not isinstance(value, bool) and value in ROTATIONS:
                settings[key] = value
            else:
                _drop("settings", key, value, "must be 0, 90, 180 or 270")
        elif key == "sensors_on":
            if isinstance(value, bool):
                settings[key] = value
            else:
                _drop("settings", key, value, "must be true or false")
        else:
            _drop("settings", key, value, "unknown key")
    return settings


def build(sections):
    """{name: section dict} -> the document dict to save."""
    doc = {"v": VERSION}
    for name, section in sections.items():
        doc[name] = section
    return doc


def merge(saved, imported):
    """The saved document with each section present in ``imported`` replaced
    by the imported one: a file with only ``settings`` keeps the saved pond,
    and one with only ``pond`` keeps the saved settings."""
    doc = build({})
    if saved:
        for name in SECTIONS:
            if name in saved:
                doc[name] = saved[name]
    for name, section in imported.items():
        if name in SECTIONS:
            doc[name] = section
        elif name != "v":
            _drop("state", name, section, "unknown section")
    return doc


def dumps(doc, pretty=False):
    if pretty:
        return _pretty(doc, "") + "\n"
    return json.dumps(doc)


def _keys(d):
    """d's keys, KEY_ORDER first."""
    keys = [k for k in KEY_ORDER if k in d]
    keys.extend(k for k in d if k not in KEY_ORDER)
    return keys


def _compact(value):
    """One-line JSON with the keys in KEY_ORDER."""
    if isinstance(value, dict):
        return (
            "{"
            + ", ".join(json.dumps(k) + ": " + _compact(value[k]) for k in _keys(value))
            + "}"
        )
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_compact(item) for item in value) + "]"
    return json.dumps(value)


def _pretty(value, indent):
    """Indented JSON. CircuitPython's json has no ``indent``, so this is done
    by hand. Objects open up one key per line; a list puts each item on its
    own line, compact, so each fish of the pond reads as one line."""
    inner = indent + "  "
    if isinstance(value, dict) and value:
        items = [
            inner + json.dumps(key) + ": " + _pretty(value[key], inner)
            for key in _keys(value)
        ]
        return "{\n" + ",\n".join(items) + "\n" + indent + "}"
    if isinstance(value, (list, tuple)) and value:
        items = [inner + _compact(item) for item in value]
        return "[\n" + ",\n".join(items) + "\n" + indent + "]"
    return json.dumps(value)
