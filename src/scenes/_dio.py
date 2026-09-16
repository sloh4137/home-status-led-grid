"""Graphics API shim: real displayio on hardware, virtual_matrix on desktop.

Scene modules do::

    from scenes._dio import dio

then use ``dio.Group``, ``dio.Bitmap``, ``dio.Palette`` and ``dio.TileGrid``.
``sim/virtual_matrix.py`` deliberately mirrors displayio's class names, so
scene code runs unmodified against either.

Import order matters: on the MatrixPortal ``displayio`` is builtin and wins.
On the desktop it raises ImportError and we fall back to the simulator, which
requires ``sim/`` on ``sys.path`` (``sim/run.py`` arranges this).

Side benefit: ``pip install adafruit-blinka-displayio`` on the desktop gives
you genuine displayio classes, so ``sim/run.py --backend sim`` then exercises
your scenes against the *real* API -- catching places where the simulator is
more forgiving than hardware.
"""

try:
    import displayio as dio  # CircuitPython hardware (MatrixPortal)
except ImportError:
    try:
        import virtual_matrix as dio  # desktop simulator (needs sim/ on sys.path)
    except ImportError as e:
        raise ImportError(
            "scenes need either CircuitPython 'displayio' or the desktop "
            "'virtual_matrix' module (add sim/ to sys.path)"
        ) from e
