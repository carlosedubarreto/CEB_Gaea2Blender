"""
Property definitions for CEB_Gaea2Blender add-on.
Stores terrain dimensions, subdivision settings, file paths, and scan results.
"""

import os
import bpy
from bpy.props import (
    StringProperty,
    FloatProperty,
    IntProperty,
    BoolProperty,
    EnumProperty,
    PointerProperty,
    CollectionProperty
)
from . import utils


def get_available_folder_files(self, context):
    """
    Dynamic Enum callback returning files from the selected Gaea folder
    matching the slot type (images for texture maps, meshes for 3D mesh).
    """
    items = [('NONE', "(Select from folder)", "No image selected for this slot", 'X', 0)]
    if not context:
        return items

    scene = getattr(context, 'scene', None)
    if not scene:
        return items

    props = getattr(scene, 'gaea_terrain_props', None)
    if not props or not props.folder_path:
        return items

    folder = bpy.path.abspath(props.folder_path)
    if not os.path.isdir(folder):
        return items

    try:
        entries = sorted(os.listdir(folder))
    except Exception:
        return items

    is_mesh = (self.category == 'Mesh')
    valid_exts = utils.SUPPORTED_MESH_EXTS if is_mesh else utils.SUPPORTED_IMAGE_EXTS

    idx = 1
    found_ids = set()
    for entry in entries:
        ext = os.path.splitext(entry)[1].lower()
        if ext in valid_exts:
            full_path = os.path.join(folder, entry)
            if os.path.isfile(full_path):
                icon_name = 'MESH_DATA' if is_mesh else 'IMAGE_DATA'
                items.append((entry, entry, full_path, icon_name, idx))
                found_ids.add(entry)
                idx += 1

    # In case self.filename is already set and not in current folder entries
    if self.filename and self.filename != "[Not Found]" and self.filename not in found_ids:
        items.append((self.filename, self.filename, self.filepath, 'FILE', idx))

    return items


def update_slot_file(self, context):
    """
    Update callback when the user selects a file from the dropdown.
    Updates filename, filepath, is_assigned, and synchronizes to direct property on props.
    """
    if not context or not hasattr(context, 'scene'):
        return
    props = getattr(context.scene, 'gaea_terrain_props', None)
    if not props:
        return

    folder = bpy.path.abspath(props.folder_path) if props.folder_path else ""

    if self.selected_file == 'NONE':
        self.filename = "[Not Found]"
        self.filepath = ""
        self.is_assigned = False
    else:
        self.filename = self.selected_file
        self.filepath = os.path.join(folder, self.selected_file) if folder else self.selected_file
        self.is_assigned = True

    # Synchronize back to direct property on props
    cat_to_prop = {
        'Height': 'detected_height_path',
        'Normal': 'detected_normal_path',
        'Albedo': 'detected_albedo_path',
        'Roughness': 'detected_roughness_path',
        'AO': 'detected_ao_path',
        'Mesh': 'detected_mesh_path',
    }
    prop_name = cat_to_prop.get(self.category)
    if prop_name and hasattr(props, prop_name):
        setattr(props, prop_name, self.filepath if self.is_assigned else "")

    # Synchronize used status for Unused items
    used_files = utils.get_used_filenames(props)
    for it in getattr(props, 'map_items', []):
        if it.category == 'Unused':
            it.is_assigned = (it.filename in used_files)


class GaeaMapCorrespondenceItem(bpy.types.PropertyGroup):
    """Stores correspondence information for a detected Gaea output file"""
    category: StringProperty(name="Category", default="")
    slot_name: StringProperty(name="Slot Name", default="")
    filename: StringProperty(name="File Name", default="")
    filepath: StringProperty(name="File Path", default="", subtype='FILE_PATH')
    destination: StringProperty(name="Destination in Blender", default="")
    icon_name: StringProperty(name="Icon", default="IMAGE_DATA")
    is_assigned: BoolProperty(name="Assigned", default=True)
    selected_file: EnumProperty(
        name="File",
        description="Select an image or mesh file from the scanned folder for this slot",
        items=get_available_folder_files,
        update=update_slot_file
    )


class GaeaTerrainProperties(bpy.types.PropertyGroup):
    # Map Correspondences collection
    map_items: CollectionProperty(type=GaeaMapCorrespondenceItem)
    # Folder Path
    folder_path: StringProperty(
        name="Gaea Output Folder",
        description="Select the folder containing QuadSpinner Gaea generated files",
        default="",
        subtype='DIR_PATH'
    )

    # Scan metadata
    scan_status: StringProperty(
        name="Scan Status",
        default="No folder scanned yet."
    )
    has_scanned: BoolProperty(
        name="Has Scanned",
        default=False
    )
    found_mesh_count: IntProperty(default=0)
    found_image_count: IntProperty(default=0)
    show_dimension_settings: BoolProperty(
        name="Show Terrain Dimensions",
        description="Toggle display of terrain dimension settings",
        default=True
    )
    show_map_correspondences: BoolProperty(
        name="Show Detected Maps Correspondence",
        description="Toggle display of detected map correspondences",
        default=True
    )
    show_geometry_settings: BoolProperty(
        name="Show Geometry & Subdivisions",
        description="Toggle display of geometry and subdivision settings",
        default=False
    )
    show_material_settings: BoolProperty(
        name="Show Material & Shading",
        description="Toggle display of material and shading settings",
        default=False
    )
    show_file_slots: BoolProperty(
        name="Show Detected File Slots",
        description="Expand to view or manually override detected file slots",
        default=False
    )

    # Terrain Dimensions
    terrain_width: FloatProperty(
        name="Width (X)",
        description="Terrain horizontal width in meters along the X axis",
        default=5000.0,
        min=0.1,
        soft_max=100000.0,
        unit='LENGTH'
    )
    terrain_length: FloatProperty(
        name="Length (Y)",
        description="Terrain length in meters along the Y axis",
        default=5000.0,
        min=0.1,
        soft_max=100000.0,
        unit='LENGTH'
    )
    terrain_height: FloatProperty(
        name="Elevation (Z)",
        description="Terrain maximum height/elevation in meters along the Z axis",
        default=2500.0,
        min=0.01,
        soft_max=50000.0,
        unit='LENGTH'
    )
    terrain_origin: EnumProperty(
        name="Origin",
        description="Origin point positioning for the generated or imported terrain",
        items=[
            ('CENTER', "Center", "Place terrain origin at the center of the bounding box"),
            ('CORNER', "Bottom-Left Corner", "Place terrain origin at the bottom-left (0,0)"),
        ],
        default='CENTER'
    )

    # Import / Geometry Mode
    import_mode: EnumProperty(
        name="Terrain Source",
        description="Select whether to build terrain from Height Map or import 3D Mesh",
        items=[
            ('HEIGHTMAP', "Height Map", "Generate plane grid and apply heightmap displacement modifier", 'IMAGE_DATA', 0),
            ('MESH', "3D Mesh", "Import native 3D mesh (ignores terrain dimension settings)", 'MESH_DATA', 1),
            ('AUTO', "Auto Detect", "Automatically imports mesh if found; otherwise generates heightmap plane", 'NONE', 2),
        ],
        default='HEIGHTMAP'
    )

    # Subdivision & Heightmap Resolution
    base_subdivisions: IntProperty(
        name="Base Subdivisions",
        description="Initial vertex density per edge for the base plane (e.g. 64 = 64x64 vertices)",
        default=64,
        min=2,
        max=4096
    )
    subdiv_levels_viewport: IntProperty(
        name="Viewport Subdiv",
        description="Subdivision Surface levels for real-time viewport heightmap detail",
        default=4,
        min=0,
        max=10
    )
    subdiv_levels_render: IntProperty(
        name="Render Subdiv",
        description="Subdivision Surface levels for high-resolution render heightmap detail",
        default=6,
        min=0,
        max=12
    )
    subdiv_type: EnumProperty(
        name="Subdivision Type",
        description="Algorithm used for mesh subdivision",
        items=[
            ('SIMPLE', "Simple", "Keeps sharp terrain boundary edges (recommended for heightmaps)"),
            ('CATMULL_CLARK', "Catmull-Clark", "Smooths edges while subdividing"),
        ],
        default='SIMPLE'
    )
    use_cycles_adaptive: BoolProperty(
        name="Cycles Micro-displacement",
        description="Configure Cycles experimental true displacement for render-time detail",
        default=False
    )

    # Shading & Material Settings
    smooth_shading: BoolProperty(
        name="Smooth Shading",
        description="Enable smooth shading across terrain polygons",
        default=True
    )
    mix_ambient_occlusion: BoolProperty(
        name="Mix AO Map",
        description="Multiply Ambient Occlusion texture with Base Color",
        default=True
    )
    ao_factor: FloatProperty(
        name="AO Factor",
        description="Strength of Ambient Occlusion blend",
        default=0.8,
        min=0.0,
        max=1.0
    )
    default_roughness: FloatProperty(
        name="Roughness Value",
        description="Roughness value to use when no roughness texture map is assigned",
        default=1.0,
        min=0.0,
        max=1.0
    )
    mesh_keep_aspect: BoolProperty(
        name="Keep Aspect Ratio",
        description="Preserve horizontal aspect ratio when scaling imported mesh",
        default=False
    )
    auto_frame_view: BoolProperty(
        name="Auto Frame View",
        description="Automatically show the full view of the scene (Home key) when loading terrain",
        default=True
    )


    # Detected File Paths (slots can be manually overridden by user)
    detected_mesh_path: StringProperty(
        name="Mesh File",
        description="Path to detected Gaea 3D mesh (.obj, .fbx, .ply)",
        subtype='FILE_PATH'
    )
    detected_height_path: StringProperty(
        name="Heightmap",
        description="Path to detected heightmap (.exr, .png, .tif)",
        subtype='FILE_PATH'
    )
    detected_normal_path: StringProperty(
        name="Normal Map",
        description="Path to detected normal map",
        subtype='FILE_PATH'
    )
    detected_albedo_path: StringProperty(
        name="Albedo / Color",
        description="Path to detected diffuse/color map",
        subtype='FILE_PATH'
    )
    detected_roughness_path: StringProperty(
        name="Roughness Map",
        description="Path to detected roughness map",
        subtype='FILE_PATH'
    )
    detected_ao_path: StringProperty(
        name="AO Map",
        description="Path to detected ambient occlusion map",
        subtype='FILE_PATH'
    )


classes = (
    GaeaMapCorrespondenceItem,
    GaeaTerrainProperties,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.gaea_terrain_props = PointerProperty(type=GaeaTerrainProperties)


def unregister():
    del bpy.types.Scene.gaea_terrain_props
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
