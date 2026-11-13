"""Save the board's state document from its serial console to a file.

    python3 tools/pull_state.py /dev/ttyACM0            # -> state.json
    python3 tools/pull_state.py COM5 -o board.json      # Windows Python

The board prints its state between ---STATE BEGIN--- / ---STATE END--- at
startup and when DUMP STATE is selected in the menu. This waits for those
markers (up to --timeout seconds): press RESET or select DUMP STATE while it
waits. The JSON is checked before it is written.

Edit the file, then put it back with ``./deploy.sh --state FILE`` (or drag it
onto CIRCUITPY as state.json); the auto-reload imports it.

On WSL2 the board's serial port isn't visible without usbipd; run this with
Windows Python against COMn instead, or copy the text between the markers
from any serial terminal (Mu, PuTTY, tio).

Needs pyserial (requirements.txt).
"""

import argparse
import json
import sys
import time

BEGIN = "---STATE BEGIN---"
END = "---STATE END---"


def read_state(port, timeout_s):
    """The text between the markers, or None on timeout."""
    import serial  # pyserial

    deadline = time.monotonic() + timeout_s
    lines = None
    with serial.Serial(port, 115200, timeout=0.5) as ser:
        while time.monotonic() < deadline:
            raw = ser.readline()
            if not raw:
                continue
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if line.strip() == BEGIN:
                lines = []  # (re)start: a reset mid-dump prints it again
            elif line.strip() == END and lines is not None:
                return "\n".join(lines) + "\n"
            elif lines is not None:
                lines.append(line)
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("port", help="serial port, e.g. /dev/ttyACM0 or COM5")
    parser.add_argument(
        "-o", "--output", default="state.json", help="file to write (default: state.json)"
    )
    parser.add_argument(
        "--timeout", type=float, default=30, help="seconds to wait (default: 30)"
    )
    args = parser.parse_args(argv)

    print(
        "Waiting up to %.0f s on %s: press RESET or select DUMP STATE..."
        % (args.timeout, args.port)
    )
    text = read_state(args.port, args.timeout)
    if text is None:
        print("No state seen on %s" % args.port, file=sys.stderr)
        return 1
    try:
        json.loads(text)
    except ValueError as e:
        print("The dump isn't valid JSON (%s):\n%s" % (e, text), file=sys.stderr)
        return 1
    with open(args.output, "w") as f:
        f.write(text)
    print("Wrote %s (%d bytes)" % (args.output, len(text)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
