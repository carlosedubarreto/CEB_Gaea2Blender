bl_info = {
    "name": "CEB Gaea to Blender Importer",
    "author": "Carlos Barreto, Antigravity",
    "version": (1, 2, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Gaea Tab",
    "description": "Scan QuadSpinner Gaea output folders to import terrains (meshes, heightmap planes, or multi-tile grids) with custom dimensions, subdivision controls, and automated PBR shading.",
    "warning": "",
    "doc_url": "",
    "category": "Import-Export",
}

## v1.02
# - add option to load maps, like snow, wear and others
# - create a material to load the color map as reference for the colors in the landscape but use a procedural way to color the landscape


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
