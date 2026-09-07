"""
Utility functions for CEB_Gaea2Blender add-on.
Handles file scanning, classification heuristics, terrain grid generation,
mesh scaling, modifier displacement, and material network construction.
"""

import os
import re
import bpy
import bmesh
from mathutils import Vector

SUPPORTED_MESH_EXTS = {'.obj', '.fbx', '.ply', '.glb', '.gltf'}
SUPPORTED_IMAGE_EXTS = {'.exr', '.png', '.tif', '.tiff', '.tga', '.jpg', '.jpeg', '.bmp', '.hdr'}

# Regex patterns for identifying Gaea map outputs
PATTERNS = {
    'height': re.compile(r'(?:^|[_\-\s\.])(height(?:field)?|disp(?:lace(?:ment)?)?|elevation|dem|hmap|h)(?:[_\-\s\.]|$)', re.IGNORECASE),
    'normal': re.compile(r'(?:^|[_\-\s\.])(normals?|norm|nrm|bump)(?:[_\-\s\.]|$)', re.IGNORECASE),
    'albedo': re.compile(r'(?:^|[_\-\s\.])(albedo|diffuse|basecolor|base_color|color|colour|col|sat|satmap|texture|cartography|carto)(?:[_\-\s\.]|$)', re.IGNORECASE),
    'roughness': re.compile(r'(?:^|[_\-\s\.])(roughness|rough|rgh)(?:[_\-\s\.]|$)', re.IGNORECASE),
    'ao': re.compile(r'(?:^|[_\-\s\.])(ao|ambient(?:_occlusion)?|occlusion)(?:[_\-\s\.]|$)', re.IGNORECASE),
    'mask': re.compile(r'(?:^|[_\-\s\.])(mask|foliage|tree|trees|rock|rocks|snow|ice|vegetation|biome|slope|curvature)(?:[_\-\s\.]|$)', re.IGNORECASE),
}


def classify_file(filename):
    """
    Classify a single filename into a Gaea category.
    Returns (category, extension) or (None, None).
    """
    name, ext = os.path.splitext(filename)
    ext_lower = ext.lower()

    if ext_lower in SUPPORTED_MESH_EXTS:
        return 'mesh', ext_lower

    if ext_lower in SUPPORTED_IMAGE_EXTS:
        for cat in ['height', 'normal', 'albedo', 'roughness', 'ao', 'mask']:
            if PATTERNS[cat].search(name):
                return cat, ext_lower

        # Fallback heuristic: EXR or 16/32-bit TIFF without explicit category might be height
        if ext_lower in {'.exr', '.tif', '.tiff'} and ('height' in name.lower() or 'disp' in name.lower()):
            return 'height', ext_lower

        # Unmatched image file (does not match any specific map or mask keyword)
        return 'unmatched', ext_lower

    return None, None


def scan_gaea_folder(folder_path):
    """
    Scan a directory for Gaea exported terrain assets.
    Returns a dictionary of categorized filepaths.
    """
    results = {
        'mesh': [],
        'height': [],
        'normal': [],
        'albedo': [],
        'roughness': [],
        'ao': [],
        'masks': [],
        'unmatched': [],
        'all_images': []
    }

    if not folder_path or not os.path.isdir(folder_path):
        return results

    try:
        entries = sorted(os.listdir(folder_path))
    except Exception as e:
        print(f"[CEB_Gaea2Blender] Error reading folder: {e}")
        return results

    for entry in entries:
        full_path = os.path.join(folder_path, entry)
        if not os.path.isfile(full_path):
            continue

        cat, ext = classify_file(entry)
        if not cat:
            continue

        if cat == 'mesh':
            results['mesh'].append(full_path)
        elif cat in {'height', 'normal', 'albedo', 'roughness', 'ao'}:
            results[cat].append(full_path)
            results['all_images'].append(full_path)
        elif cat == 'mask':
            results['masks'].append(full_path)
            results['all_images'].append(full_path)
        elif cat == 'unmatched':
            results['unmatched'].append(full_path)
            results['all_images'].append(full_path)

    return results


def get_used_filenames(props):
    """
    Returns a set of filenames (basenames) currently actively assigned/used in props.
    Excludes items with category == 'Unused'.
    """
    used = set()
    if not props:
        return used

    for item in getattr(props, 'map_items', []):
        if item.category != 'Unused' and item.is_assigned:
            if item.selected_file and item.selected_file != 'NONE':
                used.add(item.selected_file)
            if item.filename and item.filename != '[Not Found]':
                used.add(item.filename)
            if item.filepath:
                used.add(os.path.basename(item.filepath))

    override_attrs = [
        'override_height_path', 'override_normal_path', 'override_albedo_path',
        'override_roughness_path', 'override_ao_path', 'override_mesh_path'
    ]
    for attr in override_attrs:
        val = getattr(props, attr, "")
        if val:
            used.add(os.path.basename(bpy.path.abspath(val)))

    return used


def load_image_safely(filepath, colorspace='Non-Color'):
    """
    Safely load an image into Blender and set colorspace.
    """
    if not filepath or not os.path.exists(filepath):
        return None

    try:
        img = bpy.data.images.load(filepath, check_existing=True)
        # Verify if colorspace exists in current Blender OCIO config
        try:
            img.colorspace_settings.name = colorspace
        except Exception:
            # Fallback if specific colorspace name is missing in OCIO
            pass
        return img
    except Exception as e:
        print(f"[CEB_Gaea2Blender] Failed to load image {filepath}: {e}")
        return None


def create_terrain_grid(name="Gaea_Terrain", width=2048.0, length=2048.0,
                        base_subdivisions=64, origin_type='CENTER', smooth=True):
    """
    Create a quad grid plane with exact dimensions and base subdivisions using bmesh.
    Adds normalized UV coordinates [0, 1].
    """
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()

    res_x = max(2, int(base_subdivisions))
    res_y = max(2, int(base_subdivisions))

    verts = []
    for iy in range(res_y):
        v_row = []
        v_coord = iy / (res_y - 1)
        if origin_type == 'CENTER':
            y_pos = (v_coord - 0.5) * length
        else:  # CORNER
            y_pos = v_coord * length

        for ix in range(res_x):
            u_coord = ix / (res_x - 1)
            if origin_type == 'CENTER':
                x_pos = (u_coord - 0.5) * width
            else:  # CORNER
                x_pos = u_coord * width

            vert = bm.verts.new((x_pos, y_pos, 0.0))
            v_row.append(vert)
        verts.append(v_row)

    bm.verts.ensure_lookup_table()

    # Create faces
    uv_layer = bm.loops.layers.uv.new("UVMap")
    for iy in range(res_y - 1):
        for ix in range(res_x - 1):
            v0 = verts[iy][ix]
            v1 = verts[iy][ix + 1]
            v2 = verts[iy + 1][ix + 1]
            v3 = verts[iy + 1][ix]

            face = bm.faces.new((v0, v1, v2, v3))
            face.smooth = smooth

            # Set UVs
            for loop in face.loops:
                v = loop.vert
                u = (v.co.x / width + 0.5) if origin_type == 'CENTER' else (v.co.x / width)
                v_uv = (v.co.y / length + 0.5) if origin_type == 'CENTER' else (v.co.y / length)
                loop[uv_layer].uv = (u, v_uv)

    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(name, mesh)
    obj["is_gaea_terrain"] = True
    obj["gaea_type"] = "Heightmap Plane"
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    return obj


def scale_imported_mesh(obj, target_width=2048.0, target_length=2048.0,
                       target_height=500.0, origin_type='CENTER', keep_aspect=False):
    """
    Scale an imported mesh object to match target terrain dimensions.
    """
    if not obj or obj.type != 'MESH':
        return

    # Calculate bounding box in local coordinate space
    bbox_corners = [Vector(corner) for corner in obj.bound_box]
    min_x = min(c.x for c in bbox_corners)
    max_x = max(c.x for c in bbox_corners)
    min_y = min(c.y for c in bbox_corners)
    max_y = max(c.y for c in bbox_corners)
    min_z = min(c.z for c in bbox_corners)
    max_z = max(c.z for c in bbox_corners)

    cur_w = max_x - min_x
    cur_l = max_y - min_y
    cur_h = max_z - min_z

    if cur_w <= 0.0001: cur_w = 1.0
    if cur_l <= 0.0001: cur_l = 1.0
    if cur_h <= 0.0001: cur_h = 1.0

    if keep_aspect:
        scale_horizontal = ((target_width / cur_w) + (target_length / cur_l)) / 2.0
        scale_x = scale_horizontal
        scale_y = scale_horizontal
    else:
        scale_x = target_width / cur_w
        scale_y = target_length / cur_l

    scale_z = target_height / cur_h

    # Adjust origin before or after scale
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    if origin_type == 'CENTER':
        bpy.ops.object.origin_set(type='ORIGIN_CENTER_OF_MASS', center='BOUNDS')
    elif origin_type == 'BOTTOM_CENTER':
        # Shift origin to bottom of bounding box
        bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='BOUNDS')

    obj.scale = (scale_x, scale_y, scale_z)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj["is_gaea_terrain"] = True
    obj["gaea_type"] = "Imported Mesh"


def setup_height_displacement(obj, height_image_path, terrain_height=500.0,
                              subdiv_viewport=4, subdiv_render=6,
                              subdiv_type='SIMPLE'):
    """
    Adds a Subdivision Surface modifier followed by a Displace modifier
    configured with the Gaea heightmap.
    """
    if not obj or not height_image_path or not os.path.exists(height_image_path):
        return None

    img = load_image_safely(height_image_path, colorspace='Non-Color')
    if not img:
        return None

    # Create Texture datablock for displace modifier
    tex_name = f"Gaea_Height_{obj.name}"
    tex = bpy.data.textures.get(tex_name)
    if not tex:
        tex = bpy.data.textures.new(name=tex_name, type='IMAGE')
    tex.image = img
    tex.extension = 'EXTEND'

    # Subdivision modifier
    subsurf_name = "Gaea_Subdivision"
    subsurf = obj.modifiers.get(subsurf_name)
    if not subsurf:
        subsurf = obj.modifiers.new(name=subsurf_name, type='SUBSURF')

    subsurf.subdivision_type = subdiv_type
    subsurf.levels = subdiv_viewport
    subsurf.render_levels = subdiv_render

    # Displace modifier
    disp_name = "Gaea_Displacement"
    disp = obj.modifiers.get(disp_name)
    if not disp:
        disp = obj.modifiers.new(name=disp_name, type='DISPLACE')

    disp.texture = tex
    disp.direction = 'Z'
    disp.texture_coords = 'UV'
    disp.mid_level = 0.0  # In Gaea, 0.0 is base level, 1.0 is peak
    disp.strength = terrain_height

    return disp


def build_terrain_material(obj, detected_maps, terrain_height=500.0,
                           use_cycles_displacement=False, mix_ao=True, ao_factor=0.8,
                           default_roughness=1.0):
    """
    Builds a complete PBR node network for the terrain object.
    Supports Albedo (sRGB color map), Roughness (with configurable default value),
    Normal Map, AO mixing, Height (Cycles displacement), and auxiliary data masks.
    """
    if not obj:
        return None

    mat_name = f"M_Gaea_{obj.name}"
    mat = bpy.data.materials.get(mat_name)
    if not mat:
        mat = bpy.data.materials.new(name=mat_name)
    mat.use_nodes = True

    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    # Base coordinates
    pos_x = -800
    pos_y = 300

    # Output & Principled BSDF
    node_out = nodes.new(type='ShaderNodeOutputMaterial')
    node_out.location = (400, 200)

    node_bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
    node_bsdf.location = (50, 200)
    links.new(node_bsdf.outputs['BSDF'], node_out.inputs['Surface'])

    # 1. Albedo / Base Color (Color Map - sRGB)
    albedo_img = None
    node_albedo = None
    if detected_maps.get('albedo'):
        albedo_img = load_image_safely(detected_maps['albedo'], colorspace='sRGB')
        if albedo_img:
            try:
                albedo_img.colorspace_settings.name = 'sRGB'
            except Exception:
                pass
            node_albedo = nodes.new(type='ShaderNodeTexImage')
            node_albedo.image = albedo_img
            node_albedo.label = "Albedo / Base Color"
            node_albedo.location = (pos_x, 300)

    # 2. Ambient Occlusion
    ao_img = None
    node_ao = None
    if detected_maps.get('ao'):
        ao_img = load_image_safely(detected_maps['ao'], colorspace='Non-Color')
        if ao_img:
            node_ao = nodes.new(type='ShaderNodeTexImage')
            node_ao.image = ao_img
            node_ao.label = "Ambient Occlusion"
            node_ao.location = (pos_x, 50)

    # Connect Albedo & AO
    if node_albedo and node_ao and mix_ao:
        # Mix Color Node (multiply AO over Albedo)
        mix_node = nodes.new(type='ShaderNodeMix')
        mix_node.data_type = 'RGBA'
        mix_node.blend_type = 'MULTIPLY'
        mix_node.location = (pos_x + 400, 250)
        mix_node.inputs['Factor'].default_value = ao_factor
        links.new(node_albedo.outputs['Color'], mix_node.inputs[6])  # Color A / Input A
        links.new(node_ao.outputs['Color'], mix_node.inputs[7])      # Color B / Input B
        links.new(mix_node.outputs[2], node_bsdf.inputs['Base Color']) # Result -> Base Color
    elif node_albedo:
        links.new(node_albedo.outputs['Color'], node_bsdf.inputs['Base Color'])
    elif node_ao:
        links.new(node_ao.outputs['Color'], node_bsdf.inputs['Base Color'])

    # 3. Roughness
    if detected_maps.get('roughness'):
        rough_img = load_image_safely(detected_maps['roughness'], colorspace='Non-Color')
        if rough_img:
            node_rough = nodes.new(type='ShaderNodeTexImage')
            node_rough.image = rough_img
            node_rough.label = "Roughness"
            node_rough.location = (pos_x, -200)
            if 'Roughness' in node_bsdf.inputs:
                links.new(node_rough.outputs['Color'], node_bsdf.inputs['Roughness'])
    else:
        # No roughness map assigned: use configured default roughness value (defaults to 1.0)
        if 'Roughness' in node_bsdf.inputs:
            node_bsdf.inputs['Roughness'].default_value = default_roughness

    # 4. Normal Map
    if detected_maps.get('normal'):
        normal_img = load_image_safely(detected_maps['normal'], colorspace='Non-Color')
        if normal_img:
            node_norm_tex = nodes.new(type='ShaderNodeTexImage')
            node_norm_tex.image = normal_img
            node_norm_tex.label = "Normal Map"
            node_norm_tex.location = (pos_x, -450)

            node_norm_map = nodes.new(type='ShaderNodeNormalMap')
            node_norm_map.location = (pos_x + 350, -450)
            node_norm_map.space = 'TANGENT'

            links.new(node_norm_tex.outputs['Color'], node_norm_map.inputs['Color'])
            if 'Normal' in node_bsdf.inputs:
                links.new(node_norm_map.outputs['Normal'], node_bsdf.inputs['Normal'])

    # 5. Cycles Microdisplacement setup (if requested)
    if use_cycles_displacement and detected_maps.get('height'):
        height_img = load_image_safely(detected_maps['height'], colorspace='Non-Color')
        if height_img:
            node_height_tex = nodes.new(type='ShaderNodeTexImage')
            node_height_tex.image = height_img
            node_height_tex.label = "Height (Cycles True Displacement)"
            node_height_tex.location = (pos_x, -700)

            node_disp = nodes.new(type='ShaderNodeDisplacement')
            node_disp.location = (pos_x + 350, -700)
            node_disp.inputs['Height'].default_value = 0.0
            node_disp.inputs['Midlevel'].default_value = 0.0
            node_disp.inputs['Scale'].default_value = terrain_height

            links.new(node_height_tex.outputs['Color'], node_disp.inputs['Height'])
            links.new(node_disp.outputs['Displacement'], node_out.inputs['Displacement'])

            # Enable displacement in material cycles settings
            try:
                mat.cycles.displacement = 'BOTH'
            except Exception:
                pass

    # 6. Auxiliary masks placed for user convenience
    aux_y = -950
    for idx, mask_path in enumerate(detected_maps.get('masks', [])):
        mask_img = load_image_safely(mask_path, colorspace='Non-Color')
        if mask_img:
            node_mask = nodes.new(type='ShaderNodeTexImage')
            node_mask.image = mask_img
            base_filename = os.path.splitext(os.path.basename(mask_path))[0]
            node_mask.label = f"Mask: {base_filename}"
            node_mask.location = (pos_x, aux_y)
            aux_y -= 250

    # Assign material to object
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

    return mat


def configure_scene_and_viewport(scene=None, min_clip_end=100000.0):
    """
    Ensure scene units are set to Metric (Meters) and update 3D Viewport clip_end
    (and scene camera clip_end) to at least min_clip_end (default 100,000 meters)
    so large terrains are fully visible without clipping.
    """
    if not scene:
        scene = bpy.context.scene

    # 1. Set scene unit to Metric Meters
    if scene and hasattr(scene, "unit_settings"):
        scene.unit_settings.system = 'METRIC'
        scene.unit_settings.length_unit = 'METERS'
        scene.unit_settings.scale_length = 1.0

    # 2. Update active space if available
    try:
        space_data = getattr(bpy.context, 'space_data', None)
        if space_data and space_data.type == 'VIEW_3D':
            if space_data.clip_end < min_clip_end:
                space_data.clip_end = min_clip_end
    except Exception:
        pass

    # 3. Update all 3D Viewport spaces across all screens and windows
    try:
        for screen in bpy.data.screens:
            for area in screen.areas:
                if area.type == 'VIEW_3D':
                    for space in area.spaces:
                        if space.type == 'VIEW_3D' and space.clip_end < min_clip_end:
                            space.clip_end = min_clip_end
    except Exception:
        pass

    # 4. Also check active scene camera clip_end so renders don't clip
    if scene and scene.camera and hasattr(scene.camera.data, "clip_end"):
        if scene.camera.data.clip_end < min_clip_end:
            scene.camera.data.clip_end = min_clip_end


def frame_scene_view():
    """
    Automatically adjust 3D Viewport(s) to show the full view of the scene
    (equivalent of pressing the Home button / Frame All in the 3D Viewport).
    Iterates through all 3D Viewport areas and temporarily overrides the context
    to the WINDOW region so view3d.view_all() executes reliably.
    """
    success = False

    wm = getattr(bpy.context, "window_manager", None)
    windows = getattr(wm, "windows", []) if wm else []
    if not windows and getattr(bpy.context, "window", None):
        windows = [bpy.context.window]

    for window in windows:
        screen = getattr(window, "screen", None)
        if not screen:
            continue
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                win_region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                if win_region:
                    try:
                        if hasattr(bpy.context, "temp_override"):
                            with bpy.context.temp_override(window=window, screen=screen, area=area, region=win_region):
                                bpy.ops.view3d.view_all(use_all_regions=False)
                        else:
                            override = {
                                'window': window,
                                'screen': screen,
                                'area': area,
                                'region': win_region,
                                'scene': bpy.context.scene,
                            }
                            bpy.ops.view3d.view_all(override, use_all_regions=False)
                        success = True
                    except Exception as e:
                        print(f"[CEB_Gaea2Blender] Viewport frame_all failed: {e}")

    # Fallback if windows iteration didn't succeed
    if not success:
        try:
            for screen in bpy.data.screens:
                for area in screen.areas:
                    if area.type == 'VIEW_3D':
                        win_region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                        if win_region:
                            if hasattr(bpy.context, "temp_override"):
                                with bpy.context.temp_override(screen=screen, area=area, region=win_region):
                                    bpy.ops.view3d.view_all(use_all_regions=False)
                            else:
                                override = {
                                    'screen': screen,
                                    'area': area,
                                    'region': win_region,
                                    'scene': bpy.context.scene,
                                }
                                bpy.ops.view3d.view_all(override, use_all_regions=False)
                            success = True
        except Exception:
            pass

    return success


def is_gaea_terrain(obj):
    """
    Check if an object is an imported Gaea terrain mesh or a generated heightmap plane.
    """
    if not obj or obj.type != 'MESH':
        return False

    # Check custom tags
    if obj.get("is_gaea_terrain"):
        return True

    # Check for Gaea modifiers
    if "Gaea_Displacement" in obj.modifiers or "Gaea_Subdivision" in obj.modifiers:
        return True

    # Check object name
    if obj.name.startswith("Gaea_Terrain"):
        return True

    # Check assigned materials
    if obj.data.materials and any(m and m.name.startswith("M_Gaea") for m in obj.data.materials):
        return True

    return False


def update_terrain_maps(obj, detected_maps, terrain_height=500.0,
                        subdiv_viewport=4, subdiv_render=6, subdiv_type='SIMPLE',
                        use_cycles_disp=False, mix_ao=True, ao_factor=0.8,
                        default_roughness=1.0):
    """
    Updates the heightmap displacement modifier (if present) and rebuilds/updates
    the PBR material network on an existing Gaea terrain object using the newly selected maps.
    """
    if not is_gaea_terrain(obj):
        return False

    # 1. Update Heightmap Displacement if object has displace modifier or a heightmap is assigned
    disp_mod = obj.modifiers.get("Gaea_Displacement")
    height_path = detected_maps.get('height')

    if disp_mod and height_path and os.path.exists(height_path):
        img = load_image_safely(height_path, colorspace='Non-Color')
        if img:
            tex_name = f"Gaea_Height_{obj.name}"
            tex = bpy.data.textures.get(tex_name)
            if not tex:
                tex = bpy.data.textures.new(name=tex_name, type='IMAGE')
            tex.image = img
            tex.extension = 'EXTEND'
            disp_mod.texture = tex
            disp_mod.strength = terrain_height

    # Update subdivision modifier levels if present
    subsurf_mod = obj.modifiers.get("Gaea_Subdivision")
    if subsurf_mod:
        subsurf_mod.levels = subdiv_viewport
        subsurf_mod.render_levels = subdiv_render
        subsurf_mod.subdivision_type = subdiv_type

    # 2. Update / Rebuild PBR Material with the new maps
    build_terrain_material(
        obj=obj,
        detected_maps=detected_maps,
        terrain_height=terrain_height,
        use_cycles_displacement=use_cycles_disp,
        mix_ao=mix_ao,
        ao_factor=ao_factor,
        default_roughness=default_roughness
    )

    return True


