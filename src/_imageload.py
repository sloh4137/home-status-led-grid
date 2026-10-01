"""Image loading shim: adafruit_imageload backed by whichever ``dio`` is active.

Scene modules do::

    from _imageload import load_image

    bitmap, palette = load_image("sprites/pond_water.bmp")

``adafruit_imageload`` is pure Python, so the same library runs on both
targets. On the MatrixPortal it lives in ``/lib``; on the desktop install it
with ``pip install adafruit-circuitpython-imageload``.

Left to itself, imageload builds ``displayio.Bitmap``/``Palette`` objects,
which don't exist on the desktop. This shim always passes ``dio``'s classes,
so the result can go straight into ``dio.TileGrid`` on either target.
"""

from _dio import dio

try:
    import adafruit_imageload
except ImportError as e:
    raise ImportError(
        "image loading needs 'adafruit_imageload' (copy it to /lib on the "
        "board, or pip install adafruit-circuitpython-imageload on desktop)"
    ) from e


def load_image(file_or_filename):
    """Load a .bmp (or other imageload-supported image) as ``(bitmap, palette)``."""
    return adafruit_imageload.load(
        file_or_filename, bitmap=dio.Bitmap, palette=dio.Palette
    )
