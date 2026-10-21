"""AIPE CAD Agent: parametric FreeCAD geometry for power-electronics converters.

Layout
------
* ``aipe_cad.params``   pure standard-library parameter models, validation and
  derived-geometry rules (SI units, metres).  Importable both by the system
  Python and by the Python interpreter embedded in ``freecadcmd``.
* ``aipe_cad.schemas``  JSON Schema (draft 2020-12) documents for every kind.
* ``aipe_cad.freecad``  worker modules executed *inside* ``freecadcmd``; they
  build solids in millimetres and export FCStd/STEP/metadata/check reports.
* ``aipe_cad.runner``   spawns ``freecadcmd`` from the system Python.
* ``aipe_cad.cli``      the ``aipe-cad`` command line interface.
"""

__version__ = "0.1.0"

KINDS = ("transformer", "heatsink", "coldplate", "assembly")
