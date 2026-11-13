"""The saved JSON document and its validation.

    {
      "v": 1,
      "settings": {"rotation": 90, "sensors_on": true}
    }

Each section has an owner (App owns ``settings``; the pond will own ``pond``).
Loading puts the defaults first, then overlays each known field that is
valid, so old saves keep working when fields are added. Unknown keys and
invalid values are dropped, with the reason printed on the serial console.
An unparseable document means defaults.
"""

import json

VERSION = 1

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


def dumps(doc, pretty=False):
    if pretty:
        # CPython only; CircuitPython's json has no indent
        return json.dumps(doc, indent=2) + "\n"
    return json.dumps(doc)
