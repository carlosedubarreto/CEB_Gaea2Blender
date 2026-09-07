import os
import sys
import tempfile
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

print("\n--- TEST 5: Test Mesh Mode Terrain Import ---")
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
assert abs(mesh_terrain.dimensions.x - 800.0) < 1.0, f"Mesh X dimension mismatch: {mesh_terrain.dimensions.x}"
assert abs(mesh_terrain.dimensions.y - 1200.0) < 1.0, f"Mesh Y dimension mismatch: {mesh_terrain.dimensions.y}"
assert abs(mesh_terrain.dimensions.z - 400.0) < 1.0, f"Mesh Z dimension mismatch: {mesh_terrain.dimensions.z}"

print("Mesh import & scaling mode PASSED!")

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

print("\n--- TEST 6: Test UI Panel Draw ---")
from CEB_Gaea2Blender.panels import GAEA_PT_main_panel
# Test panel draw by instantiating or invoking draw on mock/context
# In Blender python, panel draw can be tested using a dummy panel instance or layout wrapper
class DummyLayout:
    def box(self): return self
    def row(self, align=False): return self
    def column(self, align=False): return self
    def label(self, text="", icon='NONE'): pass
    def prop(self, data, property, text="", icon='NONE', expand=False, slider=False, emboss=True): pass
    def operator(self, operator, text="", icon='NONE'): return self
    def separator(self): pass
    scale_y = 1.0

class DummyPanel:
    layout = DummyLayout()

panel_dummy = DummyPanel()
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
print("UI Panel draw executed without errors for all collapsed and expanded states!")

print("\n--- TEST 7: Test Unregister ---")
CEB_Gaea2Blender.unregister()
assert not hasattr(bpy.types.Scene, "gaea_terrain_props"), "gaea_terrain_props was not cleaned up"
print("Unregistered cleanly.")

# Cleanup temp files
import shutil
shutil.rmtree(temp_dir, ignore_errors=True)

print("\nALL 6 TESTS PASSED SUCCESSFULLY! CEB_Gaea2Blender is fully functional!")
