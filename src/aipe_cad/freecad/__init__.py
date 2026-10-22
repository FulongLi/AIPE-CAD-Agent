"""FreeCAD worker modules.

Everything in this package is executed *inside* ``freecadcmd`` (FreeCAD's
embedded Python) and therefore imports ``FreeCAD`` / ``Part`` lazily.  The
system Python only needs the path of :mod:`aipe_cad.freecad.worker`.

Geometry here is built in millimetres (FreeCAD's internal unit) from resolved
parameter dictionaries in SI units; conversion happens through
:func:`aipe_cad.units.m_to_mm` at the boundary.
"""
