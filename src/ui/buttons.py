"""Side buttons -> menu gestures.

The MatrixPortal has UP, DOWN and RESET. RESET is a hardware reset that
reboots the chip, so code can't read it; only UP and DOWN are used:

- tap UP / tap DOWN (released before HOLD_S): TAP_UP / TAP_DOWN
- hold either button for HOLD_S: HOLD, fired once while still held; the
  release that ends a hold is ignored

Every button source has ``poll(now)``, which returns the gestures since the
last call as a list (reused between calls; read it before the next poll).

- ``KeypadButtons``: the real buttons, through ``keypad.Keys`` (debounced
  and scanned in the background)
- ``SimButtons``: the desktop simulator; key presses map straight to
  gestures (Up/Down = tap, Enter/Space = HOLD), so X11 auto-repeat can't fake
  a hold
- ``NoButtons``: nothing to read
"""

TAP_UP = "TAP_UP"
TAP_DOWN = "TAP_DOWN"
HOLD = "HOLD"

UP = 0
DOWN = 1
HOLD_S = 0.6

_TAPS = (TAP_UP, TAP_DOWN)


class ButtonGestures:
    """Pure gesture logic for the UP (0) and DOWN (1) keys. Feed it key
    changes with ``feed()`` and call ``update()`` every frame so a hold fires
    while the button is still down."""

    def __init__(self, hold_s=HOLD_S):
        self.hold_s = hold_s
        self._down_at = [None, None]  # press time per key, None when up
        self._held = [False, False]  # HOLD already fired for this press
        self.out = []

    def feed(self, key, pressed, t):
        if pressed:
            self._down_at[key] = t
            self._held[key] = False
            return
        if self._down_at[key] is None:
            return
        self._down_at[key] = None
        if not self._held[key]:
            self.out.append(_TAPS[key])

    def update(self, t):
        for key in (UP, DOWN):
            down_at = self._down_at[key]
            if (
                down_at is not None
                and not self._held[key]
                and t - down_at >= self.hold_s
            ):
                self._held[key] = True
                self.out.append(HOLD)


class KeypadButtons:
    """The MatrixPortal's UP / DOWN buttons (hardware only)."""

    def __init__(self, hold_s=HOLD_S):
        import board
        import keypad

        # Key numbers follow the pin order: 0 = UP, 1 = DOWN
        self._keys = keypad.Keys(
            (board.BUTTON_UP, board.BUTTON_DOWN),
            value_when_pressed=False,
            pull=True,
        )
        self._event = keypad.Event()  # reused, so draining doesn't allocate
        self._gestures = ButtonGestures(hold_s)

    def poll(self, now):
        gestures = self._gestures
        gestures.out.clear()
        events = self._keys.events
        event = self._event
        while events.get_into(event):
            gestures.feed(event.key_number, event.pressed, now)
        gestures.update(now)
        return gestures.out


class SimButtons:
    """Simulator keys. Pass ``key`` to VirtualDisplay.on_key()."""

    KEYS = {
        "Up": TAP_UP,
        "Down": TAP_DOWN,
        "Return": HOLD,
        "KP_Enter": HOLD,
        "space": HOLD,
    }

    def __init__(self):
        self._pending = []
        self._out = []

    def key(self, keysym):
        gesture = self.KEYS.get(keysym)
        if gesture is not None:
            self._pending.append(gesture)

    def poll(self, now):
        self._out, self._pending = self._pending, self._out
        self._pending.clear()
        return self._out


class NoButtons:
    _none = ()

    def poll(self, now):
        return self._none
