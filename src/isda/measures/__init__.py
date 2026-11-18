"""Measures, registered at import.

Each claim measure declares the perturbations that must move it and the null
model it is read against. Importing this package registers every measure
module: registration is an import-time act, so the registry's contents are
exactly the modules named here. A module not imported here does not exist to
the registry, the assertion runner, or the pin builder. Add new measure
modules to this list.
"""

from . import arithmetica_cpidr as arithmetica_cpidr
from . import astronomia as astronomia
from . import geometry as geometry
from . import inventory as inventory
from . import musica as musica
from . import shape as shape
