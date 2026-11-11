"""Text menu driven by the button gestures in ui.buttons.

While hidden, any gesture opens the menu. While visible, a tap moves the
highlight (wrapping) and HOLD runs the highlighted item. Items are
``(label_fn, action_fn)``; label_fn() is called each time the menu is drawn,
so labels like SENSORS ON/OFF follow the current state.
"""

from ui.buttons import HOLD, TAP_DOWN, TAP_UP

MARKER = "> "
NO_MARKER = "  "


class Menu:
    def __init__(self, items):
        self.items = items
        self.visible = False
        self.index = 0

    def handle(self, gesture):
        """Apply one gesture. Returns True if the menu (or anything an action
        changed) may need redrawing."""
        if not self.visible:
            self.visible = True
            return True
        if gesture == TAP_UP:
            self.index = (self.index - 1) % len(self.items)
        elif gesture == TAP_DOWN:
            self.index = (self.index + 1) % len(self.items)
        elif gesture == HOLD:
            self.items[self.index][1]()
        else:
            return False
        return True

    def hide(self):
        self.visible = False

    def lines(self):
        return [
            (MARKER if i == self.index else NO_MARKER) + label_fn()
            for i, (label_fn, _) in enumerate(self.items)
        ]
