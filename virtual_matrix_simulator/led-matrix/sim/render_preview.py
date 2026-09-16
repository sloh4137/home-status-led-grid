"""Headless preview renderer: draws the fish tank scene to an animated GIF.

Usage:  python3 sim/render_preview.py [--width 64] [--height 64]
Writes: previews/fish_tank.gif

Same scene code as the interactive sim -- just composited into PIL images
instead of a tkinter window, so it can run anywhere (including headless).
Renders each LED as a separate dot with gaps, like the real panel.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import virtual_matrix as vm
from fish_tank import create_scene

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "previews", "fish_tank.gif")
CELL = 7  # screen px per LED in the GIF
PAD = 1   # gap around each LED dot


def render_frame(pixels, width, height):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (width * CELL, height * CELL), (11, 11, 13))
    draw = ImageDraw.Draw(img)
    for y in range(height):
        for x in range(width):
            r, g, b = pixels[y * width + x]
            if r or g or b:
                draw.ellipse(
                    [x * CELL + PAD, y * CELL + PAD,
                     (x + 1) * CELL - PAD - 1, (y + 1) * CELL - PAD - 1],
                    fill=(r, g, b),
                )
    return img


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--width", type=int, default=64)
    parser.add_argument("--height", type=int, default=64)
    parser.add_argument("--frames", type=int, default=48)
    parser.add_argument("--fps", type=int, default=12)
    args = parser.parse_args()

    group, update = create_scene(args.width, args.height)
    dt = 1.0 / args.fps
    images = []
    for _ in range(args.frames):
        update(dt)
        pixels = vm.composite(group, args.width, args.height)
        images.append(render_frame(pixels, args.width, args.height))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    images[0].save(
        OUT, save_all=True, append_images=images[1:],
        duration=int(1000 / args.fps), loop=0,
    )
    print("wrote", OUT, "(%d frames, %dx%d)" % (args.frames, args.width, args.height))


if __name__ == "__main__":
    main()
