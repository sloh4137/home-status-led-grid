"""Shared LED-matrix scenes, backend-agnostic.

Each scene module exposes:

    create_scene(width, height) -> (group, update)

where ``group`` is a displayio-style Group and ``update`` advances the
animation by ``dt`` seconds. Scene code only uses the graphics API from
``scenes._dio`` (real ``displayio`` on the MatrixPortal, ``virtual_matrix``
on the desktop), so the same files run in the simulator and on hardware.

Desktop entry points must put both the project root (for ``scenes``) and
``sim/`` (for ``virtual_matrix``) on ``sys.path`` -- see ``sim/run.py``.
On the MatrixPortal, copy this whole ``scenes/`` folder to the CIRCUITPY
drive next to ``code.py``.
"""
