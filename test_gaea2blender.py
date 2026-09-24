import os
import sys
import tempfile
import shutil
import bpy

# Add addon directory to sys.path
ADDON_DIR = r"d:\_Code\Meu\CEB_Gaea2Blender_prj"
if ADDON_DIR not in sys.path:
    sys.path.insert(0, ADDON_DIR)

print("\n--- TEST 1: Register and Unregister Addon ---")
import CEB_Gaea2Blender
CEB_Gaea2Blender.register()
print("Registered successfully.")
assert hasattr(bpy.types.Scene, "gaea_terrain_props"), "Scene does not have gaea_terrain_props"

print("\n--- TEST 2: Create Dummy Gaea Directory and Files ---")
temp_dir = tempfile.mkdtemp(prefix="gaea_test_")
print(f"Temp folder: {temp_dir}")

# Create dummy texture files (using Blender's image API to generate valid images)
img_types = {
    "Alpine_Height.exr": (32, 32, 1),
    "Alpine_Normal.png": (32, 32, 4),
    "Alpine_Albedo.png": (32, 32, 4),
    "Alpine_Roughness.png": (32, 32, 1),
    "Alpine_AO.png": (32, 32, 1),
    "Reference_Photo.png": (32, 32, 4),
}

for filename, (w, h, channels) in img_types.items():
    filepath = os.path.join(temp_dir, filename)
    b_img = bpy.data.images.new(name=filename, width=w, height=h, alpha=(channels == 4))
    b_img.filepath_raw = filepath
    b_img.file_format = 'OPEN_EXR' if filename.endswith('.exr') else 'PNG'
    b_img.save()
    bpy.data.images.remove(b_img)
    print(f"Created dummy image: {filename}")

# Create a dummy OBJ file
obj_path = os.path.join(temp_dir, "Alpine_Mesh.obj")
with open(obj_path, "w") as f:
    f.write("""v -10.0 -10.0 0.0
v 10.0 -10.0 0.0
v 10.0 10.0 5.0
v -10.0 10.0 5.0
vn 0.0 0.0 1.0
vt 0.0 0.0
vt 1.0 0.0
vt 1.0 1.0
vt 0.0 1.0
f 1/1/1 2/2/1 3/3/1 4/4/1
""")
print("Created dummy OBJ file.")

print("\n--- TEST 3: Test Folder Scanning ---")
scene = bpy.context.scene
props = scene.gaea_terrain_props
props.folder_path = temp_dir

res = bpy.ops.gaea.scan_folder()
assert res == {'FINISHED'}, f"Scan folder failed with {res}"
print(f"Scan Status: {props.scan_status}")
print(f"Detected Height: {props.detected_height_path}")
print(f"Detected Normal: {props.detected_normal_path}")
print(f"Detected Albedo: {props.detected_albedo_path}")
print(f"Detected Roughness: {props.detected_roughness_path}")
print(f"Detected AO: {props.detected_ao_path}")
print(f"Detected Mesh: {props.detected_mesh_path}")

assert "Alpine_Height.exr" in props.detected_height_path, "Heightmap not detected correctly"
assert "Alpine_Normal.png" in props.detected_normal_path, "Normal map not detected correctly"
assert "Alpine_Albedo.png" in props.detected_albedo_path, "Albedo not detected correctly"
assert "Alpine_Roughness.png" in props.detected_roughness_path, "Roughness not detected correctly"
assert "Alpine_AO.png" in props.detected_ao_path, "AO not detected correctly"
assert "Alpine_Mesh.obj" in props.detected_mesh_path, "Mesh not detected correctly"

# Verify correspondence items
print(f"Map items count: {len(props.map_items)}")
assert len(props.map_items) >= 7, f"Expected at least 7 correspondence items, got {len(props.map_items)}"
for item in props.map_items:
    status_str = f"Mapped -> '{item.filename}' ({item.destination})" if item.is_assigned else f"Unassigned / {item.category}"
    print(f"  [Slot: {item.slot_name}] {status_str}")

# Verify unmatched file Reference_Photo.png was NOT put as Mask, but as Unused
ref_item = next((it for it in props.map_items if it.filename == "Reference_Photo.png"), None)
assert ref_item is not None, "Reference_Photo.png should be listed in map_items"
assert ref_item.category == "Unused", f"Expected Reference_Photo.png to have category 'Unused', got '{ref_item.category}'"
assert not ref_item.is_assigned, "Reference_Photo.png should not be assigned as a mask"
print("Verified: Reference_Photo.png correctly categorized as Unused (NOT as a mask)!")

print("All Gaea outputs classified and correspondences populated with 100% accuracy!")

# Verify Normals_Out and Cartography_Out classification
from CEB_Gaea2Blender import utils
assert utils.classify_file("Normals_Out.png")[0] == 'normal', "Normals_Out.png should be classified as normal"
assert utils.classify_file("Cartography_Out.png")[0] == 'albedo', "Cartography_Out.png should be classified as albedo"
assert utils.classify_file("Terrain_Normals_Out.exr")[0] == 'normal', "Terrain_Normals_Out.exr should be classified as normal"
assert utils.classify_file("Terrain_Cartography_Out.png")[0] == 'albedo', "Terrain_Cartography_Out.png should be classified as albedo"
print("Verified: 'Normals_Out' matches normal and 'Cartography_Out' matches albedo!")

print("\n--- TEST 3b: Test Dropdown Selection on Missing / Available Slots & Dynamic Unused List ---")
from CEB_Gaea2Blender import utils
used_files_init = utils.get_used_filenames(props)
assert "Reference_Photo.png" not in used_files_init, "Reference_Photo.png should not be in used_files initially"
unused_items_init = [i for i in props.map_items if i.category == 'Unused' and not i.is_assigned and i.filename not in used_files_init]
assert any(i.filename == "Reference_Photo.png" for i in unused_items_init), "Reference_Photo.png should be in unused_items initially"
print(f"Initially unused files: {[i.filename for i in unused_items_init]}")

ao_item = next((it for it in props.map_items if it.category == 'AO'), None)
assert ao_item is not None, "AO item not found in map_items"

# Simulate AO slot being missing / unassigned
ao_item.selected_file = 'NONE'
assert not ao_item.is_assigned, "AO item should be unassigned when NONE is selected"
assert props.detected_ao_path == "", "detected_ao_path should be empty"
print("Slot successfully set to unassigned [NONE]")

# User selects an unused file from folder via dropdown (e.g. Reference_Photo.png)
ao_item.selected_file = 'Reference_Photo.png'
assert ao_item.is_assigned, "AO item should be assigned after selection"
assert ao_item.filename == 'Reference_Photo.png', f"Expected Reference_Photo.png, got {ao_item.filename}"

# Verify Reference_Photo.png is now used and removed from unused_items
used_files_now = utils.get_used_filenames(props)
assert "Reference_Photo.png" in used_files_now, "Reference_Photo.png should now be in used_files"
unused_items_now = [i for i in props.map_items if i.category == 'Unused' and not i.is_assigned and i.filename not in used_files_now]
assert not any(i.filename == "Reference_Photo.png" for i in unused_items_now), "Reference_Photo.png must be removed from unused list when used!"
print("Verified: Reference_Photo.png was successfully removed from unused list when used!")

# Restore back to Alpine_AO.png
ao_item.selected_file = 'Alpine_AO.png'
assert ao_item.filename == 'Alpine_AO.png'
used_files_restored = utils.get_used_filenames(props)
assert "Reference_Photo.png" not in used_files_restored, "Reference_Photo.png should no longer be in used_files"
unused_items_restored = [i for i in props.map_items if i.category == 'Unused' and not i.is_assigned and i.filename not in used_files_restored]
assert any(i.filename == "Reference_Photo.png" for i in unused_items_restored), "Reference_Photo.png should return to unused_items when no longer used"
print("Verified: Reference_Photo.png returned to unused list when no longer used!")

print("\n--- TEST 4: Test Heightmap Mode Terrain Import ---")
props.import_mode = 'HEIGHTMAP'
props.terrain_width = 1000.0
props.terrain_length = 1500.0
props.terrain_height = 350.0
props.base_subdivisions = 16
props.subdiv_levels_viewport = 3
props.subdiv_levels_render = 5
props.subdiv_type = 'SIMPLE'

# Clear any existing objects in scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Test unit setting and clip end before import
scene.unit_settings.system = 'IMPERIAL'

res = bpy.ops.gaea.import_terrain()
assert res == {'FINISHED'}, f"Import terrain failed with {res}"

# Verify scene units were set to METRIC and METERS
assert scene.unit_settings.system == 'METRIC', f"Expected METRIC, got {scene.unit_settings.system}"
assert scene.unit_settings.length_unit == 'METERS', f"Expected METERS, got {scene.unit_settings.length_unit}"
print("Scene units verified: METRIC / METERS")

# Verify all VIEW_3D spaces have clip_end >= 100000.0
for sc in bpy.data.screens:
    for a in sc.areas:
        if a.type == 'VIEW_3D':
            for s in a.spaces:
                if s.type == 'VIEW_3D':
                    assert s.clip_end >= 100000.0, f"Expected clip_end >= 100000, got {s.clip_end}"
print("Viewport clip_end >= 100,000m verified!")

terrain_obj = bpy.data.objects.get("Gaea_Terrain")
assert terrain_obj is not None, "Gaea_Terrain object was not created"
print(f"Created object: {terrain_obj.name}")
print(f"Object dimensions: X={terrain_obj.dimensions.x:.2f}m, Y={terrain_obj.dimensions.y:.2f}m")
assert abs(terrain_obj.dimensions.x - 1000.0) < 1e-2, f"Expected width 1000, got {terrain_obj.dimensions.x}"
assert abs(terrain_obj.dimensions.y - 1500.0) < 1e-2, f"Expected length 1500, got {terrain_obj.dimensions.y}"

# Check Modifiers
subsurf = terrain_obj.modifiers.get("Gaea_Subdivision")
assert subsurf is not None, "Subdivision modifier missing"
assert subsurf.levels == 3, f"Expected viewport subdiv 3, got {subsurf.levels}"
assert subsurf.render_levels == 5, f"Expected render subdiv 5, got {subsurf.render_levels}"
assert subsurf.subdivision_type == 'SIMPLE', "Subdiv type should be SIMPLE"

disp = terrain_obj.modifiers.get("Gaea_Displacement")
assert disp is not None, "Displacement modifier missing"
assert disp.strength == 350.0, f"Expected displacement strength 350.0, got {disp.strength}"
assert disp.direction == 'Z', "Displacement direction should be Z"

# Check Material and Nodes
mat = terrain_obj.data.materials[0]
assert mat is not None, "Material not assigned"
assert mat.use_nodes, "Material should use nodes"
node_names = [n.label or n.name for n in mat.node_tree.nodes]
print("Material nodes:", node_names)

albedo_node = next((n for n in mat.node_tree.nodes if "Albedo" in (n.label or n.name)), None)
assert albedo_node is not None, "Albedo node missing"
assert albedo_node.image.colorspace_settings.name == 'sRGB', f"Expected Albedo colorspace sRGB, got {albedo_node.image.colorspace_settings.name}"
print("Albedo colorspace verified as sRGB color map!")

assert any("Normal" in name for name in node_names), "Normal node missing"
assert any("Roughness" in name for name in node_names), "Roughness node missing"
assert not any("Reference_Photo" in name for name in node_names), "Reference_Photo must NOT be added as a mask node in material!"
print("Verified: Unmatched file Reference_Photo is not in shader material nodes!")

print("Heightmap plane mode PASSED!")

print("\n--- TEST 4b: Test Updating Maps on Selected Heightmap Terrain ---")
bpy.context.view_layer.objects.active = terrain_obj
assert CEB_Gaea2Blender.utils.is_gaea_terrain(terrain_obj), "terrain_obj should be recognized as Gaea terrain"

props.terrain_height = 550.0
props.subdiv_levels_viewport = 2
# Test removing roughness map to verify default_roughness fallback (default 1.0)
props.detected_roughness_path = ""
props.default_roughness = 1.0
res_update = bpy.ops.gaea.update_terrain_maps()
assert res_update == {'FINISHED'}, f"Update terrain maps failed with {res_update}"
assert disp.strength == 550.0, f"Expected displacement strength 550.0, got {disp.strength}"
assert subsurf.levels == 2, f"Expected viewport subdiv 2, got {subsurf.levels}"

bsdf_node = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
assert abs(bsdf_node.inputs['Roughness'].default_value - 1.0) < 1e-3, f"Expected default roughness 1.0, got {bsdf_node.inputs['Roughness'].default_value}"
print("Default roughness value (1.0) verified when no roughness map is set!")
print("Heightmap terrain maps & modifiers successfully updated!")

print("\n--- TEST 5: Test Mesh Mode Terrain Import (Ignoring Terrain Dimensions) ---")
props.import_mode = 'MESH'
props.terrain_width = 800.0
props.terrain_length = 1200.0
props.terrain_height = 400.0

# Clear scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

res = bpy.ops.gaea.import_terrain()
assert res == {'FINISHED'}, f"Mesh import failed with {res}"

mesh_terrain = bpy.context.active_object
assert mesh_terrain is not None, "Mesh terrain not found"
print(f"Imported mesh: {mesh_terrain.name}")
print(f"Dimensions: X={mesh_terrain.dimensions.x:.2f}m, Y={mesh_terrain.dimensions.y:.2f}m, Z={mesh_terrain.dimensions.z:.2f}m")
# Verify that terrain dimension settings (800x1200x400) are IGNORED and native mesh dimensions (20x20x5) are preserved
assert abs(mesh_terrain.dimensions.x - 20.0) < 1.0, f"Mesh X dimension mismatch: {mesh_terrain.dimensions.x} (expected native 20m)"
assert abs(mesh_terrain.dimensions.y - 20.0) < 1.0, f"Mesh Y dimension mismatch: {mesh_terrain.dimensions.y} (expected native 20m)"
assert abs(mesh_terrain.dimensions.z - 5.0) < 1.0, f"Mesh Z dimension mismatch: {mesh_terrain.dimensions.z} (expected native 5m)"

# Verify UV map was automatically generated on the imported mesh
assert len(mesh_terrain.data.uv_layers) >= 1, "Imported mesh must have at least one UV layer"
active_uv = mesh_terrain.data.uv_layers.active
assert active_uv is not None, "Mesh must have an active UV layer"
print(f"Verified: Mesh has active UV layer '{active_uv.name}' with {len(active_uv.data)} loop coordinates!")
for i in range(len(active_uv.data)):
    u, v = active_uv.data[i].uv
    assert -1e-4 <= u <= 1.0 + 1e-4, f"UV U out of [0, 1] bounds: {u}"
    assert -1e-4 <= v <= 1.0 + 1e-4, f"UV V out of [0, 1] bounds: {v}"
print("Verified: UV coordinates are correctly normalized to [0, 1]!")

# Verify Texture Coordinate node in material and connection to Albedo
mesh_mat = mesh_terrain.data.materials[0]
texcoord_node = next((n for n in mesh_mat.node_tree.nodes if n.type == 'TEX_COORD'), None)
assert texcoord_node is not None, "Material missing ShaderNodeTexCoord node"
mesh_albedo = next((n for n in mesh_mat.node_tree.nodes if "Albedo" in (n.label or n.name)), None)
assert mesh_albedo is not None, "Albedo node missing in mesh material"
albedo_vector_link = next((link for link in mesh_mat.node_tree.links if link.to_node == mesh_albedo and link.to_socket.name == 'Vector'), None)
assert albedo_vector_link is not None, "Albedo Vector socket must be connected"
assert albedo_vector_link.from_node == texcoord_node and albedo_vector_link.from_socket.name == 'UV', "Albedo Vector must be connected to TexCoord UV output"
print("Verified: Texture Coordinate UV output is connected to Albedo Vector socket!")

# Test gaea.generate_uv_map operator
bpy.context.view_layer.objects.active = mesh_terrain
gen_uv_res = bpy.ops.gaea.generate_uv_map()
assert gen_uv_res == {'FINISHED'}, f"gaea.generate_uv_map failed with {gen_uv_res}"
print("Verified: gaea.generate_uv_map operator executed successfully!")

print("Mesh import mode ignoring terrain dimensions and generating UVs PASSED!")

print("\n--- TEST 5b: Test Updating Maps on Selected Mesh Terrain ---")
assert CEB_Gaea2Blender.utils.is_gaea_terrain(mesh_terrain), "mesh_terrain should be recognized as Gaea terrain"
res_mesh_update = bpy.ops.gaea.update_terrain_maps()
assert res_mesh_update == {'FINISHED'}, f"Update terrain maps on mesh failed with {res_mesh_update}"
print("Mesh terrain maps successfully updated!")

print("\n--- TEST 5c: Test Auto Frame Scene View (Home button equivalent) ---")
assert hasattr(props, "auto_frame_view"), "props does not have auto_frame_view property"
assert props.auto_frame_view is True, "auto_frame_view should default to True"
frame_res = CEB_Gaea2Blender.utils.frame_scene_view()
assert frame_res is True, "frame_scene_view should return True when 3D views exist"
op_frame_res = bpy.ops.gaea.frame_view()
assert op_frame_res == {'FINISHED'}, f"gaea.frame_view operator failed with {op_frame_res}"
print("Auto frame scene view (Home) verified successfully!")

print("\n--- TEST 6: Test UI Panel Draw and Source Selector ---")
from CEB_Gaea2Blender.panels import GAEA_PT_main_panel

# Test panel draw by instantiating or invoking draw on mock/context
class DummyLayout:
    def __init__(self):
        self.recorded_props = []
    def box(self): return self
    def row(self, align=False): return self
    def column(self, align=False): return self
    def label(self, text="", icon='NONE'): pass
    def prop(self, data, property, text="", icon='NONE', **kwargs):
        if text:
            self.recorded_props.append(text)
    def prop_enum(self, data, property, value, text="", icon='NONE'): pass
    def operator(self, operator, text="", icon='NONE'): return self
    def separator(self): pass
    scale_y = 1.0
    enabled = True

class DummyPanel:
    def __init__(self):
        self.layout = DummyLayout()

panel_dummy = DummyPanel()
for mode in ('HEIGHTMAP', 'MESH'):
    props.import_mode = mode
    for show_dim in (True, False):
        for show_corr in (True, False):
            for show_geo in (True, False):
                for show_mat in (True, False):
                    props.show_dimension_settings = show_dim
                    props.show_map_correspondences = show_corr
                    props.show_geometry_settings = show_geo
                    props.show_material_settings = show_mat
                    props.show_file_slots = False
                    GAEA_PT_main_panel.draw(panel_dummy, bpy.context)

# Verify that Geometry & Subdivisions comes BEFORE Terrain Dimensions in the UI layout
panel_order_test = DummyPanel()
props.import_mode = 'HEIGHTMAP'
props.show_dimension_settings = True
props.show_geometry_settings = True
GAEA_PT_main_panel.draw(panel_order_test, bpy.context)
geo_idx = next(i for i, text in enumerate(panel_order_test.layout.recorded_props) if "Geometry & Subdivisions" in text)
dim_idx = next(i for i, text in enumerate(panel_order_test.layout.recorded_props) if "Terrain Dimensions" in text)
assert geo_idx < dim_idx, f"Expected Geometry & Subdivisions (idx {geo_idx}) to be above Terrain Dimensions (idx {dim_idx})"
print(f"Verified: UI Section Order: Geometry & Subdivisions (idx {geo_idx}) is placed on top of Terrain Dimensions (idx {dim_idx})!")
print("UI Panel draw executed without errors for all collapsed/expanded states and modes (HEIGHTMAP & MESH)!")

print("\n--- TEST 6b: Test Tiled Terrain Detection & Import (4x4 Grid) ---")
# 1. Test regex extraction
from CEB_Gaea2Blender import utils
tx, ty, cname = utils.extract_tile_coords("Terrain_y0_x0.exr")
assert (tx, ty, cname) == (0, 0, "Terrain.exr"), f"Expected (0, 0, 'Terrain.exr'), got {(tx, ty, cname)}"

tx, ty, cname = utils.extract_tile_coords("Alpine_y2_x3_Height.png")
assert (tx, ty, cname) == (3, 2, "Alpine_Height.png"), f"Expected (3, 2, 'Alpine_Height.png'), got {(tx, ty, cname)}"

tx, ty, cname = utils.extract_tile_coords("Height_x1_y3.exr")
assert (tx, ty, cname) == (1, 3, "Height.exr"), f"Expected (1, 3, 'Height.exr'), got {(tx, ty, cname)}"

tx, ty, cname = utils.extract_tile_coords("Terrain.1012.exr")
assert (tx, ty, cname) == (1, 1, "Terrain.exr"), f"Expected (1, 1, 'Terrain.exr'), got {(tx, ty, cname)}"

tx, ty, cname = utils.extract_tile_coords("tile_2_3.png")
assert (tx, ty, cname) == (2, 3, "terrain.png"), f"Expected (2, 3, 'terrain.png'), got {(tx, ty, cname)}"

tx, ty, cname = utils.extract_tile_coords("Alpine_Height.exr")
assert tx is None and ty is None, f"Non-tiled image should return None, got {tx}, {ty}"
print("Verified: Tile coordinate regex extraction handles yx, xy, UDIM, and non-tiled patterns accurately!")

# 2. Create a temporary folder with 4x4 tiled terrain (16 tiles x 4 maps = 64 files)
tiled_temp_dir = tempfile.mkdtemp(prefix="gaea_tiled_test_")
print(f"Tiled temp folder: {tiled_temp_dir}")

# Create dummy images for 4x4 grid (16 tiles)
for iy in range(4):
    for ix in range(4):
        for map_type, ext in [('Height', '.exr'), ('Normal', '.png'), ('Albedo', '.png'), ('Snow', '.png')]:
            fname = f"Terrain_y{iy}_x{ix}_{map_type}{ext}"
            fpath = os.path.join(tiled_temp_dir, fname)
            img = bpy.data.images.new(name=fname, width=16, height=16)
            img.filepath_raw = fpath
            img.file_format = 'OPEN_EXR' if ext == '.exr' else 'PNG'
            img.save()
            bpy.data.images.remove(img)

# 3. Test Scanning Tiled Directory
props.folder_path = tiled_temp_dir
res_scan = bpy.ops.gaea.scan_folder()
assert res_scan == {'FINISHED'}, f"Scan folder failed with {res_scan}"

print(f"Tiled Scan Status: {props.scan_status}")
print(f"Is Tiled: {props.is_tiled}")
print(f"Grid Info: {props.tile_grid_info}")
print(f"Tile Cols: {props.tile_cols}, Tile Rows: {props.tile_rows}, Total: {props.tile_total_count}")

assert props.is_tiled is True, "Expected props.is_tiled to be True"
assert props.tile_grid_info == "4x4 tiles", f"Expected '4x4 tiles', got '{props.tile_grid_info}'"
assert props.tile_cols == 4, f"Expected tile_cols == 4, got {props.tile_cols}"
assert props.tile_rows == 4, f"Expected tile_rows == 4, got {props.tile_rows}"
assert props.tile_total_count == 16, f"Expected tile_total_count == 16, got {props.tile_total_count}"
assert "4x4 tiles (16 total)" in props.scan_status, f"Expected '4x4 tiles (16 total)' in scan_status, got {props.scan_status}"

# Verify map_items in tiled mode
height_item = next((i for i in props.map_items if i.category == 'Height'), None)
assert height_item is not None, "Heightmap item should exist in map_items"
assert "4x4 tiles" in height_item.slot_name, f"Expected '4x4 tiles' in height_item.slot_name, got '{height_item.slot_name}'"
assert "Terrain_y0_x0_Height.exr" in height_item.filename, f"Expected 'Terrain_y0_x0_Height.exr' in filename, got '{height_item.filename}'"
assert "per Tile" in height_item.destination, f"Expected 'per Tile' in destination, got '{height_item.destination}'"
print("Verified: Tiled folder scan detected 4x4 grid and populated summary correspondence slots!")

# 4. Test Importing 4x4 Tiled Terrain (with proportional subdivision downscaling)
assert props.tile_flip_y is True, "tile_flip_y should be True by default"
props.terrain_width = 4000.0   # 4000m total width -> 1000m per tile
props.terrain_length = 4000.0  # 4000m total length -> 1000m per tile
props.terrain_height = 1000.0  # 1000m elevation
props.terrain_origin = 'CENTER'
props.base_subdivisions = 16
props.subdiv_levels_viewport = 4
props.subdiv_levels_render = 6
props.use_tiling = True
props.tile_flip_y = False
props.auto_scale_tiled_subdiv = True

# Verify mathematical downscaling function
eff_b, eff_v, eff_r = utils.get_effective_tile_subdivisions(props)
assert (eff_b, eff_v, eff_r) == (4, 2, 4), f"Expected effective (4, 2, 4), got {(eff_b, eff_v, eff_r)}"
props.auto_scale_tiled_subdiv = False
assert utils.get_effective_tile_subdivisions(props) == (16, 4, 6), "Expected unscaled values when auto_scale is False"
props.auto_scale_tiled_subdiv = True

res_import = bpy.ops.gaea.import_terrain()
assert res_import == {'FINISHED'}, f"Import tiled terrain failed with {res_import}"

# Verify root object and collection
root_obj = bpy.data.objects.get("Gaea_Terrain_Tiled_4x4")
assert root_obj is not None, "Root object 'Gaea_Terrain_Tiled_4x4' was not created"
assert root_obj.type == 'EMPTY', "Root object should be an Empty"
assert root_obj.get("is_tiled") is True, "Root object should have is_tiled == True"
assert utils.is_gaea_terrain(root_obj), "Root object should be recognized as Gaea terrain"

# Verify all 16 child tiles
child_tiles = [c for c in root_obj.children if c.type == 'MESH']
assert len(child_tiles) == 16, f"Expected 16 child tiles, got {len(child_tiles)}"

for iy in range(4):
    for ix in range(4):
        tile_name = f"Gaea_Tile_x{ix}_y{iy}"
        tile_obj = bpy.data.objects.get(tile_name)
        assert tile_obj is not None, f"Tile object '{tile_name}' was not created"
        assert tile_obj.parent == root_obj, f"Tile '{tile_name}' should be parented to root_obj"
        assert utils.is_gaea_terrain(tile_obj), f"Tile '{tile_name}' should be recognized as Gaea terrain"

        # Check dimensions: each tile plane should be exactly 1000.0m x 1000.0m
        assert abs(tile_obj.dimensions.x - 1000.0) < 0.1, f"Expected tile width 1000m, got {tile_obj.dimensions.x}"
        assert abs(tile_obj.dimensions.y - 1000.0) < 0.1, f"Expected tile length 1000m, got {tile_obj.dimensions.y}"

        # Verify downscaled base geometry: 4-vertex grid has (4-1)*(4-1) = 9 quads (instead of (16-1)^2 = 225)
        expected_polys = (eff_b - 1) ** 2
        assert len(tile_obj.data.polygons) == expected_polys, f"Expected {expected_polys} polygons per downscaled tile, got {len(tile_obj.data.polygons)}"

        # Check subdivision modifier levels (proportionally downscaled to 2 and 4 to conserve memory)
        subsurf = tile_obj.modifiers.get("Gaea_Subdivision")
        assert subsurf is not None, f"Subdivision modifier missing on tile '{tile_name}'"
        assert subsurf.levels == 2, f"Expected downscaled viewport subdiv 2, got {subsurf.levels}"
        assert subsurf.render_levels == 4, f"Expected downscaled render subdiv 4, got {subsurf.render_levels}"

        # Check displacement modifier
        disp = tile_obj.modifiers.get("Gaea_Displacement")
        assert disp is not None, f"Displacement modifier missing on tile '{tile_name}'"
        assert disp.strength == 1000.0, f"Expected displacement strength 1000m, got {disp.strength}"
        assert disp.texture is not None, f"Displacement texture missing on tile '{tile_name}'"

        # Check material
        assert len(tile_obj.data.materials) > 0, f"No material assigned to tile '{tile_name}'"
        mat = tile_obj.data.materials[0]
        assert mat.name.startswith("M_Gaea_Gaea_Tile"), f"Unexpected material name: {mat.name}"

# Check tile positioning and seamless boundary alignment
# Total terrain spans [-2000, +2000] along X and Y.
# Column 0 center X = -1500; Column 1 center X = -500; Column 2 center X = +500; Column 3 center X = +1500.
tile_0_0 = bpy.data.objects.get("Gaea_Tile_x0_y0")
tile_1_0 = bpy.data.objects.get("Gaea_Tile_x1_y0")
tile_3_3 = bpy.data.objects.get("Gaea_Tile_x3_y3")

assert abs(tile_0_0.location.x - (-1500.0)) < 0.01, f"Tile (0,0) location X incorrect: {tile_0_0.location.x}"
assert abs(tile_0_0.location.y - (-1500.0)) < 0.01, f"Tile (0,0) location Y incorrect: {tile_0_0.location.y}"
assert abs(tile_1_0.location.x - (-500.0)) < 0.01, f"Tile (1,0) location X incorrect: {tile_1_0.location.x}"
assert abs(tile_3_3.location.x - (1500.0)) < 0.01, f"Tile (3,3) location X incorrect: {tile_3_3.location.x}"
assert abs(tile_3_3.location.y - (1500.0)) < 0.01, f"Tile (3,3) location Y incorrect: {tile_3_3.location.y}"

# Verify edge alignment: right boundary of Tile 0 should be exactly left boundary of Tile 1
tile_0_right = tile_0_0.location.x + 500.0  # -1000.0
tile_1_left = tile_1_0.location.x - 500.0   # -1000.0
assert abs(tile_0_right - tile_1_left) < 1e-5, f"Boundary gap between Tile 0 and Tile 1: {tile_0_right} vs {tile_1_left}"
print("Verified: 4x4 tiled terrain generated accurately with seamless edge-to-edge alignment spanning exactly 4000m x 4000m!")
print("Verified: Geometry (base quads) and Subdivisions (viewport/render levels) downscaled proportionally for memory safety!")

# 5. Test Updating Maps on Tiled Terrain
bpy.context.view_layer.objects.active = root_obj
res_update = bpy.ops.gaea.update_terrain_maps()
assert res_update == {'FINISHED'}, f"Update maps on tiled terrain failed with {res_update}"
# Verify child modifier levels after update retain downscaled values
subsurf_check = tile_0_0.modifiers.get("Gaea_Subdivision")
assert subsurf_check.levels == 2, f"Expected viewport subdiv 2 after update, got {subsurf_check.levels}"
assert subsurf_check.render_levels == 4, f"Expected render subdiv 4 after update, got {subsurf_check.render_levels}"
print("Verified: Update terrain maps operator successfully updated all 16 tiles of tiled terrain!")

# 6. Test UI panel drawing with tiled terrain
GAEA_PT_main_panel.draw(panel_dummy, bpy.context)
print("Verified: UI panel draw executed without errors in tiled mode!")

print("\n--- TEST 6c: Test Detail / High-Res Tile Replacement ---")
# 1. Create dummy high-res detail folder for Tile (1, 2)
detail_temp_dir = tempfile.mkdtemp(prefix="gaea_detail_test_")
print(f"Detail temp folder: {detail_temp_dir}")
detail_files = {
    "Hero_Height.exr": (32, 32, 1),
    "Hero_Normal.png": (32, 32, 4),
    "Hero_Albedo.png": (32, 32, 4),
    "Hero_Roughness.png": (32, 32, 1),
}
for fname, (w, h, channels) in detail_files.items():
    fpath = os.path.join(detail_temp_dir, fname)
    img = bpy.data.images.new(name=fname, width=w, height=h, alpha=(channels == 4))
    img.filepath_raw = fpath
    img.file_format = 'OPEN_EXR' if fname.endswith('.exr') else 'PNG'
    img.save()
    bpy.data.images.remove(img)

# 2. Test scan_detail_folder
d_maps = utils.scan_detail_folder(detail_temp_dir)
assert "Hero_Height.exr" in d_maps.get('height', ''), f"Detail heightmap not found: {d_maps}"
assert "Hero_Normal.png" in d_maps.get('normal', ''), f"Detail normal not found: {d_maps}"
assert "Hero_Albedo.png" in d_maps.get('albedo', ''), f"Detail albedo not found: {d_maps}"
assert "Hero_Roughness.png" in d_maps.get('roughness', ''), f"Detail roughness not found: {d_maps}"
print("Verified: utils.scan_detail_folder successfully identified all high-res maps!")

# 3. Test gaea.pick_active_tile operator
target_tile = bpy.data.objects.get("Gaea_Tile_x1_y2")
assert target_tile is not None, "Target tile Gaea_Tile_x1_y2 not found"
bpy.context.view_layer.objects.active = target_tile
res_pick = bpy.ops.gaea.pick_active_tile()
assert res_pick == {'FINISHED'}, f"pick_active_tile failed with {res_pick}"
assert props.detail_tile_x == 1, f"Expected detail_tile_x 1, got {props.detail_tile_x}"
assert props.detail_tile_y == 2, f"Expected detail_tile_y 2, got {props.detail_tile_y}"
print("Verified: gaea.pick_active_tile correctly set detail_tile_x=1, detail_tile_y=2 from active viewport tile!")

# 4. Test gaea.apply_detail_tile operator on existing terrain with custom height scale, inversion, and flip Y
props.detail_folder_path = detail_temp_dir
props.detail_auto_match = False
props.detail_subdiv_boost = 1
props.detail_height_scale = 1.5
props.detail_invert_height = True
props.detail_mid_level = 0.25
props.detail_flip_y = True

res_apply = bpy.ops.gaea.apply_detail_tile()
assert res_apply == {'FINISHED'}, f"apply_detail_tile failed with {res_apply}"

# Verify Tile (1, 2) has boosted subdivisions and new heightmap texture
subsurf_1_2 = target_tile.modifiers.get("Gaea_Subdivision")
assert subsurf_1_2.levels == 3, f"Expected boosted viewport subdiv 3 (2+1), got {subsurf_1_2.levels}"
assert subsurf_1_2.render_levels == 5, f"Expected boosted render subdiv 5 (4+1), got {subsurf_1_2.render_levels}"

disp_1_2 = target_tile.modifiers.get("Gaea_Displacement")
assert "Hero_Height" in disp_1_2.texture.image.name, f"Expected Hero_Height texture on tile, got {disp_1_2.texture.image.name}"
assert disp_1_2.texture_coords == 'UV', f"Expected texture_coords 'UV', got '{disp_1_2.texture_coords}'"
assert disp_1_2.uv_layer == 'UVMap', f"Expected uv_layer 'UVMap', got '{disp_1_2.uv_layer}'"
assert abs(disp_1_2.strength - (-1500.0)) < 1e-3, f"Expected inverted scaled height -1500.0, got {disp_1_2.strength}"
assert abs(disp_1_2.mid_level - 0.25) < 1e-3, f"Expected midlevel 0.25, got {disp_1_2.mid_level}"
assert disp_1_2.texture.use_flip_axis is False, "Expected use_flip_axis to be False (UV orientation handles flipping)"
# Verify UV coordinates on Tile (1, 2) mesh were flipped vertically
uv_data_1_2 = target_tile.data.uv_layers['UVMap'].data
# Check that V coordinate at minimum local Y is 1.0 (inverted)
min_v_sample = uv_data_1_2[0].uv[1]
print(f"Sample V coordinate after flip: {min_v_sample}")
assert abs(min_v_sample - 1.0) < 1e-3, f"Expected flipped V coordinate 1.0, got {min_v_sample}"

# Verify other tile (0, 0) was NOT modified and retained levels (2, 4) and default displacement
subsurf_0_0 = tile_0_0.modifiers.get("Gaea_Subdivision")
assert subsurf_0_0.levels == 2, f"Tile (0, 0) levels should remain 2, got {subsurf_0_0.levels}"
assert subsurf_0_0.render_levels == 4, f"Tile (0, 0) render levels should remain 4, got {subsurf_0_0.render_levels}"
disp_0_0 = tile_0_0.modifiers.get("Gaea_Displacement")
assert abs(disp_0_0.strength - 1000.0) < 1e-3, f"Tile (0, 0) strength should be 1000.0, got {disp_0_0.strength}"

# Verify Material on Tile (1, 2) has Hero_Albedo
mat_1_2 = target_tile.data.materials[0]
albedo_node_1_2 = next((n for n in mat_1_2.node_tree.nodes if "Albedo" in (n.label or n.name)), None)
assert albedo_node_1_2 is not None and "Hero_Albedo" in albedo_node_1_2.image.name, "Hero_Albedo should be wired into tile material"
print("Verified: High-res detail folder successfully applied to Tile (1, 2) with height scale, invert height, midlevel, and flip Y!")

# Verify Idempotence: Applying detail tile repeatedly MUST NOT accumulate subdivision levels or leak memory
for repeat_i in range(5):
    res_repeat = bpy.ops.gaea.apply_detail_tile()
    assert res_repeat == {'FINISHED'}
    assert subsurf_1_2.levels == 3, f"Viewport subdiv level accumulated to {subsurf_1_2.levels} on repeat {repeat_i+1} (expected 3)"
    assert subsurf_1_2.render_levels == 5, f"Render subdiv level accumulated to {subsurf_1_2.render_levels} on repeat {repeat_i+1} (expected 5)"
print("Verified: Repeatedly applying high-res detail maps is 100% idempotent (subdivisions stay at level 3, never accumulating)!")

# 4b. Test Auto-Match Operator and Calibration
res_auto = bpy.ops.gaea.auto_match_detail()
assert res_auto == {'FINISHED'}, f"auto_match_detail failed: {res_auto}"
print(f"Auto-matched properties: Scale={props.detail_height_scale}, Midlevel={props.detail_mid_level}, Flip Y={props.detail_flip_y}")
print("Verified: gaea.auto_match_detail operator executed successfully!")

# 4c. Test gaea.apply_detail_textures_only (Keep Base Height)
props.detail_flip_y = True
res_tex_only = bpy.ops.gaea.apply_detail_textures_only()
assert res_tex_only == {'FINISHED'}, f"apply_detail_textures_only failed: {res_tex_only}"
assert props.detail_keep_original_height is True, "detail_keep_original_height should be set to True"
# Mesh UVMap should NOT be flipped
assert abs(target_tile.data.uv_layers['UVMap'].data[0].uv[1] - 0.0) < 1e-3, "Mesh UV should be un-flipped when keeping base height"
# Material should have Mapping node with Scale Y = -1
mat_nodes = target_tile.data.materials[0].node_tree.nodes
mapping_node = next((n for n in mat_nodes if n.type == 'MAPPING'), None)
assert mapping_node is not None, "Mapping node should exist in shader when flip_y=True on textures only"
assert abs(mapping_node.inputs['Scale'].default_value[1] - (-1.0)) < 1e-3, "Mapping node Scale Y should be -1.0"
print("Verified: gaea.apply_detail_textures_only correctly preserves base displacement and mesh UV while flipping texture shader mapping!")

# 5. Test Full Tiled Terrain Import with enable_tile_override = True
props.enable_tile_override = True
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

res_tiled_ov = bpy.ops.gaea.import_terrain()
assert res_tiled_ov == {'FINISHED'}, f"Import with enable_tile_override failed: {res_tiled_ov}"
new_tile_1_2 = bpy.data.objects.get("Gaea_Tile_x1_y2")
assert new_tile_1_2 is not None, "Gaea_Tile_x1_y2 not created on override import"
assert new_tile_1_2.get("is_detail_tile") is True, "new_tile_1_2 should have is_detail_tile=True"
disp_new_1_2 = new_tile_1_2.modifiers.get("Gaea_Displacement")
assert disp_new_1_2.texture.use_flip_axis is False, "Expected use_flip_axis to be False"

# 6. Verify UI Panel Drawing with Detail Override Section
GAEA_PT_main_panel.draw(panel_dummy, bpy.context)
print("Verified: UI panel draw executed with detail override controls active without error!")

# Clean up detail temp files
shutil.rmtree(detail_temp_dir, ignore_errors=True)

# Cleanup tiled temp files
shutil.rmtree(tiled_temp_dir, ignore_errors=True)

print("\n--- TEST 7: Test Unregister ---")
CEB_Gaea2Blender.unregister()
assert not hasattr(bpy.types.Scene, "gaea_terrain_props"), "gaea_terrain_props was not cleaned up"
print("Unregistered cleanly.")

# Cleanup temp files
shutil.rmtree(temp_dir, ignore_errors=True)

print("\nALL 7 TESTS PASSED SUCCESSFULLY! CEB_Gaea2Blender is fully functional!")
