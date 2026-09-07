bl_info = {
    "name": "CEB Gaea to Blender Importer",
    "author": "Carlos Barreto, Antigravity",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Gaea Tab",
    "description": "Scan QuadSpinner Gaea output folders to import terrains (meshes or heightmap planes) with custom dimensions, subdivision controls, and automated PBR shading.",
    "warning": "",
    "doc_url": "",
    "category": "Import-Export",
}

import importlib
from . import properties
from . import operators
from . import panels
from . import utils

# Support reloading in Blender when developing
if "properties" in locals():
    importlib.reload(properties)
if "operators" in locals():
    importlib.reload(operators)
if "panels" in locals():
    importlib.reload(panels)
if "utils" in locals():
    importlib.reload(utils)


def register():
    properties.register()
    operators.register()
    panels.register()


def unregister():
    panels.unregister()
    operators.unregister()
    properties.unregister()


if __name__ == "__main__":
    register()
