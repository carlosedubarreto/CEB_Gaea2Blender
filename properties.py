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


_FOLDER_CACHE = {
    'folder': None,
    'mtime': 0,
    'entries': [],
}


def clear_folder_cache():
    """Clear cached folder file entries."""
    global _FOLDER_CACHE
    _FOLDER_CACHE = {
        'folder': None,
        'mtime': 0,
        'entries': [],
    }


def get_available_folder_files(self, context):
    """
    Dynamic Enum callback returning files from the selected Gaea folder
    matching the slot type (images for texture maps, meshes for 3D mesh).
    Uses in-memory caching keyed by folder path and modification time
    to eliminate filesystem I/O overhead on UI redraws.
    """
    items = [('NONE', "(Select from folder)", "No image selected for this slot", 0)]

    scene = getattr(context, 'scene', None) if context else getattr(bpy.context, 'scene', None)
    folder = ""
    if scene:
        props = getattr(scene, 'gaea_terrain_props', None)
        if props and props.folder_path:
            folder = bpy.path.abspath(props.folder_path)

    global _FOLDER_CACHE
    if folder and os.path.isdir(folder):
        try:
            mtime = os.path.getmtime(folder)
        except Exception:
            mtime = 0

        if _FOLDER_CACHE['folder'] != folder or _FOLDER_CACHE['mtime'] != mtime:
            cached = []
            try:
                with os.scandir(folder) as it:
                    for entry in it:
                        if entry.is_file():
                            ext = os.path.splitext(entry.name)[1].lower()
                            if ext in utils.SUPPORTED_MESH_EXTS:
                                cached.append((entry.name, entry.path, True))
                            elif ext in utils.SUPPORTED_IMAGE_EXTS:
                                cached.append((entry.name, entry.path, False))
                cached.sort(key=lambda x: x[0])
                _FOLDER_CACHE['folder'] = folder
                _FOLDER_CACHE['mtime'] = mtime
                _FOLDER_CACHE['entries'] = cached
            except Exception:
                pass

    is_mesh = (getattr(self, 'category', '') == 'Mesh')
    found_names = set()
    idx = 1
    for name, path, file_is_mesh in _FOLDER_CACHE.get('entries', []):
        if file_is_mesh == is_mesh:
            items.append((name, name, path, idx))
            found_names.add(name)
            idx += 1

    # If the currently assigned file is not in the folder cache (e.g. custom or moved file),
    # preserve it with a stable high index to prevent RNA mismatch warnings without shifting other items.
    cur = getattr(self, 'filename', '')
    if cur and cur != "[Not Found]" and cur != 'NONE' and cur not in found_names:
        items.append((cur, cur, getattr(self, 'filepath', ''), 999999))

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

    # Tiled Terrain metadata & settings
    is_tiled: BoolProperty(
        name="Is Tiled Terrain",
        description="Whether the scanned folder contains tiled terrain assets",
        default=False
    )
    use_tiling: BoolProperty(
        name="Load as Tiled Terrain",
        description="Load and assemble detected tiles into a continuous coordinate-aligned terrain grid",
        default=True
    )
    tile_cols: IntProperty(
        name="Tile Columns (X)",
        description="Number of tile columns along horizontal X axis",
        default=1,
        min=1
    )
    tile_rows: IntProperty(
        name="Tile Rows (Y)",
        description="Number of tile rows along vertical Y axis",
        default=1,
        min=1
    )
    tile_total_count: IntProperty(
        name="Total Tiles",
        description="Total number of tiles in the grid",
        default=1,
        min=1
    )
    tile_grid_info: StringProperty(
        name="Tile Grid Info",
        description="Formatted tile grid summary, e.g. '4x4 tiles'",
        default=""
    )
    tile_flip_y: BoolProperty(
        name="Flip Y Row Order (Y0 at North)",
        description="Flip Y row order (enable if Y0 corresponds to the north/top of the terrain in Gaea export)",
        default=True
    )
    auto_scale_tiled_subdiv: BoolProperty(
        name="Scale Subdivisions for Tiles",
        description="Proportionally downscale base subdivisions and modifier levels per tile according to grid dimensions to prevent excessive memory usage",
        default=True
    )
    show_detail_tile_settings: BoolProperty(
        name="Show Detail Tile Settings",
        description="Toggle display of detail tile replacement settings",
        default=True
    )
    enable_tile_override: BoolProperty(
        name="Replace Tile with High-Res Folder",
        description="Use another folder containing higher-resolution maps for a specific tile",
        default=False
    )
    detail_folder_path: StringProperty(
        name="Detail Folder",
        description="Path to folder containing high-resolution replacement maps (e.g. 2k/4k) for a specific tile",
        subtype='DIR_PATH',
        default=""
    )
    detail_tile_x: IntProperty(
        name="Tile X",
        description="Column index (X) of the tile to replace (0-indexed)",
        default=0,
        min=0
    )
    detail_tile_y: IntProperty(
        name="Tile Y",
        description="Row index (Y) of the tile to replace (0-indexed)",
        default=0,
        min=0
    )
    detail_subdiv_boost: IntProperty(
        name="Extra Subdivision Levels",
        description="Additional viewport and render subdivision levels for the detailed tile",
        default=1,
        min=0,
        max=4
    )
    detail_height_scale: FloatProperty(
        name="Detail Height Scale",
        description="Height scale multiplier for the detail tile displacement (use to match elevation with neighboring tiles)",
        default=1.0,
        min=-100.0,
        max=100.0,
        step=10,
        precision=3
    )
    detail_invert_height: BoolProperty(
        name="Invert Detail Height",
        description="Invert height displacement direction for the detail tile (peaks become valleys)",
        default=False
    )
    detail_mid_level: FloatProperty(
        name="Detail Midlevel (Elevation Offset)",
        description="Displacement midlevel offset for the detail tile (0.0 = base level)",
        default=0.0,
        min=-10.0,
        max=10.0,
        step=5,
        precision=3
    )
    detail_flip_y: BoolProperty(
        name="Flip Detail Y (Vertical)",
        description="Flip the detail tile texture coordinates vertically (North/South)",
        default=False
    )
    detail_auto_match: BoolProperty(
        name="Auto-Match Elevation & Orientation",
        description="Automatically calculate height scale, midlevel offset, and orientation from base terrain",
        default=True
    )
    detail_keep_original_height: BoolProperty(
        name="Keep Original Heightmap",
        description="Preserve the tile's original heightmap and displacement modifier, replacing only the surface material textures (Albedo, Normal, AO, Roughness, and Masks)",
        default=False
    )
    tile_data_json: StringProperty(
        name="Tile Data JSON",
        description="Internal serialized mapping of tile coordinates to file paths",
        default=""
    )
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
        default=True
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
