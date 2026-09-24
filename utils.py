"""
Utility functions for CEB_Gaea2Blender add-on.
Handles file scanning, classification heuristics, terrain grid generation,
mesh scaling, modifier displacement, and material network construction.
"""

import os
import re
import json
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

# Regex patterns for identifying tile coordinates exported from Gaea
TILE_PATTERNS = [
    # Gaea 2 default: _y0_x0, _y0x0 (case insensitive)
    (re.compile(r'(?:^|[_\-\.\s])y(\d+)[_\-\.\s]?x(\d+)(?=[_\-\.\s]|\.|$)', re.IGNORECASE), 'yx'),
    # UNIGINE / Unreal / standard: _x0_y0, _x0y0
    (re.compile(r'(?:^|[_\-\.\s])x(\d+)[_\-\.\s]?y(\d+)(?=[_\-\.\s]|\.|$)', re.IGNORECASE), 'xy'),
    # Tile prefix with x and y: e.g. tile_x0_y1
    (re.compile(r'(?:^|[_\-\.\s])tile[_\-\.\s]?x(\d+)[_\-\.\s]?y(\d+)(?=[_\-\.\s]|\.|$)', re.IGNORECASE), 'xy'),
    (re.compile(r'(?:^|[_\-\.\s])tile[_\-\.\s]?y(\d+)[_\-\.\s]?x(\d+)(?=[_\-\.\s]|\.|$)', re.IGNORECASE), 'yx'),
    # Tile prefix with raw numbers: e.g. tile_0_1 or tile-0-1
    (re.compile(r'(?:^|[_\-\.\s])tile[_\-\.\s](\d+)[_\-\.\s](\d+)(?=[_\-\.\s]|\.|$)', re.IGNORECASE), 'xy'),
    # UDIM pattern: e.g. .1001. or _1001. or 1001.png (1001 to 1099)
    (re.compile(r'(?:^|[_\-\.\s])(10[0-9]{2})(?=[_\-\.\s]|\.|$)', re.IGNORECASE), 'udim'),
]


def extract_tile_coords(filename):
    """
    Attempt to extract tile (x, y) coordinates and clean base name from a filename.
    Returns (tile_x, tile_y, clean_filename) or (None, None, None).
    """
    name, ext = os.path.splitext(filename)

    for pattern, order in TILE_PATTERNS:
        m = pattern.search(name)
        if m:
            if order == 'yx':
                y = int(m.group(1))
                x = int(m.group(2))
            elif order == 'xy':
                x = int(m.group(1))
                y = int(m.group(2))
            elif order == 'udim':
                udim = int(m.group(1))
                x = (udim - 1001) % 10
                y = (udim - 1001) // 10
            else:
                continue

            # Strip matched tile coordinate substring to obtain clean filename
            span = m.span()
            prefix = name[:span[0]].rstrip('_- .')
            suffix = name[span[1]:].lstrip('_- .')
            if prefix and suffix:
                clean_base = f"{prefix}_{suffix}"
            elif prefix:
                clean_base = prefix
            elif suffix:
                clean_base = suffix
            else:
                clean_base = "terrain"

            clean_filename = f"{clean_base}{ext}"
            return x, y, clean_filename

    return None, None, None


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
    Detects both single terrains and tiled build grids (e.g. 2x2, 4x4, 8x8).
    Returns a dictionary of categorized filepaths and tile layout metadata.
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
        'all_images': [],
        # Tiled terrain metadata
        'is_tiled': False,
        'tile_cols': 0,
        'tile_rows': 0,
        'tile_total_count': 0,
        'tile_grid_info': "",
        'tiles': {},          # key: "x_y" -> dict of channel -> filepath
        'tiled_channels': {}, # key: channel_name -> list of filepaths
    }

    if not folder_path or not os.path.isdir(folder_path):
        return results

    try:
        entries = sorted(os.scandir(folder_path), key=lambda e: e.name)
    except Exception as e:
        print(f"[CEB_Gaea2Blender] Error reading folder: {e}")
        return results

    tile_entries = []

    for entry in entries:
        if not entry.is_file():
            continue

        entry_name = entry.name
        full_path = entry.path

        cat, ext = classify_file(entry_name)

        # Check if filename has tile coordinates
        tx, ty, clean_name = extract_tile_coords(entry_name)
        if tx is not None:
            # Re-classify using clean name if initial classify was unmatched or None
            if not cat or cat == 'unmatched':
                clean_cat, _ = classify_file(clean_name)
                if clean_cat and clean_cat != 'unmatched':
                    cat = clean_cat
                elif ext in {'.exr', '.tif', '.tiff'}:
                    cat = 'height'
                elif ext in SUPPORTED_IMAGE_EXTS:
                    cat = 'mask'
                elif ext in SUPPORTED_MESH_EXTS:
                    cat = 'mesh'

            if cat:
                tile_entries.append((tx, ty, cat, clean_name, full_path, entry_name))

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

    # Process and detect tile grid
    if tile_entries:
        coords_set = {(item[0], item[1]) for item in tile_entries}
        # Folder is tiled if at least 2 distinct tile coordinates are found, or coordinate is non-zero
        if len(coords_set) > 1 or any(c[0] > 0 or c[1] > 0 for c in coords_set):
            results['is_tiled'] = True
            max_x = max(c[0] for c in coords_set)
            max_y = max(c[1] for c in coords_set)
            results['tile_cols'] = max_x + 1
            results['tile_rows'] = max_y + 1
            results['tile_total_count'] = results['tile_cols'] * results['tile_rows']
            results['tile_grid_info'] = f"{results['tile_cols']}x{results['tile_rows']} tiles"

            # Populate tile structures
            for tx, ty, cat, clean_name, full_path, orig_name in tile_entries:
                tile_key = f"{tx}_{ty}"
                if tile_key not in results['tiles']:
                    results['tiles'][tile_key] = {
                        'x': tx,
                        'y': ty,
                        'height': None,
                        'normal': None,
                        'albedo': None,
                        'roughness': None,
                        'ao': None,
                        'masks': {},
                        'mesh': None,
                    }

                t_data = results['tiles'][tile_key]
                if cat == 'mask':
                    clean_base = os.path.splitext(clean_name)[0]
                    m_mask = PATTERNS['mask'].search(clean_base)
                    mask_name = m_mask.group(1).capitalize() if m_mask else clean_base.capitalize()
                    t_data['masks'][mask_name] = full_path
                    results['tiled_channels'].setdefault(f"Mask: {mask_name}", []).append(full_path)
                else:
                    t_data[cat] = full_path
                    results['tiled_channels'].setdefault(cat, []).append(full_path)

            # Ensure tile files do not appear as unmatched unused files
            tiled_paths = {item[4] for item in tile_entries}
            results['unmatched'] = [p for p in results['unmatched'] if p not in tiled_paths]

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


def create_tile_plane_mesh(name, width, length, subdivisions=64, smooth=True):
    """
    Create a quad grid plane for a single terrain tile with local coordinates
    centered at (0, 0) and normalized UV coordinates [0, 1].
    """
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()

    res_x = max(2, int(subdivisions))
    res_y = max(2, int(subdivisions))

    verts = []
    for iy in range(res_y):
        v_row = []
        v_coord = iy / (res_y - 1)
        y_pos = (v_coord - 0.5) * length

        for ix in range(res_x):
            u_coord = ix / (res_x - 1)
            x_pos = (u_coord - 0.5) * width
            vert = bm.verts.new((x_pos, y_pos, 0.0))
            v_row.append(vert)
        verts.append(v_row)

    bm.verts.ensure_lookup_table()

    uv_layer = bm.loops.layers.uv.new("UVMap")
    for iy in range(res_y - 1):
        for ix in range(res_x - 1):
            v0 = verts[iy][ix]
            v1 = verts[iy][ix + 1]
            v2 = verts[iy + 1][ix + 1]
            v3 = verts[iy + 1][ix]

            face = bm.faces.new((v0, v1, v2, v3))
            face.smooth = smooth

            for loop in face.loops:
                u = (loop.vert.co.x / width) + 0.5
                v = (loop.vert.co.y / length) + 0.5
                loop[uv_layer].uv = (u, v)

    bm.to_mesh(mesh)
    bm.free()
    return mesh


def get_effective_tile_subdivisions(props):
    """
    Computes proportionally downscaled subdivision values for each tile in a tiled terrain
    to prevent excessive memory usage and ensure total vertex density across the entire
    terrain matches single-terrain settings.

    Returns:
        (eff_base_subdiv, eff_subdiv_viewport, eff_subdiv_render)
    """
    if not getattr(props, 'is_tiled', False) or not getattr(props, 'use_tiling', False):
        return (props.base_subdivisions, props.subdiv_levels_viewport, props.subdiv_levels_render)

    if not getattr(props, 'auto_scale_tiled_subdiv', True):
        return (props.base_subdivisions, props.subdiv_levels_viewport, props.subdiv_levels_render)

    import math
    nx = max(1, props.tile_cols)
    ny = max(1, props.tile_rows)
    max_axis_tiles = max(nx, ny)

    # Scale base subdivisions across tile axis (min 2 per tile edge)
    eff_base = max(2, int(round(props.base_subdivisions / max_axis_tiles)))

    # Each subsurf level multiplies quad count by 4 (2x per edge).
    # To keep total vertices constant across an NxN tile grid:
    # reduction = round(log2(max(nx, ny)))
    level_reduction = max(0, int(round(math.log2(max_axis_tiles)))) if max_axis_tiles > 1 else 0

    eff_viewport = max(0, props.subdiv_levels_viewport - level_reduction)
    eff_render = max(0, props.subdiv_levels_render - level_reduction)

    return (eff_base, eff_viewport, eff_render)


def scan_detail_folder(folder_path, target_x=0, target_y=0):
    """
    Scans a folder containing detailed/high-res replacement maps for a tile.
    Supports both:
      1. Single-tile exports (e.g. Height.exr, Normal.png, Albedo.png, Cartography.png)
      2. Tiled exports (e.g. Terrain_y1_x2_Height.exr, Terrain_x2_y1_Normal.png)
    Returns:
      dict: {'height': path, 'normal': path, 'albedo': path, 'roughness': path, 'ao': path, 'masks': [path, ...]}
    """
    folder_abs = bpy.path.abspath(folder_path)
    if not folder_abs or not os.path.isdir(folder_abs):
        return {}

    try:
        entries = [e.name for e in os.scandir(folder_abs) if e.is_file()]
    except Exception:
        return {}

    tiled_matches = {}
    untiled_matches = {}

    for fname in entries:
        fpath = os.path.join(folder_abs, fname)
        tx, ty, clean_name = extract_tile_coords(fname)
        category, _ = classify_file(clean_name if tx is not None else fname)

        if category in ('unused', 'unmatched', 'mesh') or category is None:
            continue

        if tx is not None and ty is not None:
            if tx == target_x and ty == target_y:
                if category == 'mask':
                    tiled_matches.setdefault('masks', []).append(fpath)
                else:
                    tiled_matches[category] = fpath
        else:
            if category == 'mask':
                untiled_matches.setdefault('masks', []).append(fpath)
            else:
                untiled_matches[category] = fpath

    # If coordinate-matched tiled files exist, prioritize them; else use untiled files
    matched = tiled_matches if tiled_matches else untiled_matches
    return matched


def set_tile_uv_orientation(tile_obj, flip_y=False):
    """
    Sets or updates the UV coordinates of a tile mesh.
    If flip_y is True, inverts the V coordinate so top-down image textures
    align with the bottom-up terrain mesh.
    """
    if not tile_obj or tile_obj.type != 'MESH' or not tile_obj.data:
        return
    mesh = tile_obj.data
    uv_layer = mesh.uv_layers.get("UVMap")
    if not uv_layer:
        uv_layer = mesh.uv_layers.new(name="UVMap")
    if not uv_layer:
        return

    # Check local bounding box
    min_x = min(v.co.x for v in mesh.vertices)
    max_x = max(v.co.x for v in mesh.vertices)
    min_y = min(v.co.y for v in mesh.vertices)
    max_y = max(v.co.y for v in mesh.vertices)
    width = max_x - min_x if max_x - min_x > 1e-5 else 1.0
    length = max_y - min_y if max_y - min_y > 1e-5 else 1.0

    uv_data = uv_layer.data
    for poly in mesh.polygons:
        for loop_idx in poly.loop_indices:
            v_idx = mesh.loops[loop_idx].vertex_index
            co = mesh.vertices[v_idx].co
            u = (co.x - min_x) / width
            v = (co.y - min_y) / length
            if flip_y:
                v = 1.0 - v
            uv_data[loop_idx].uv = (u, v)
    mesh.update()


def find_base_tile_height_path(context, props, tile_x, tile_y, exclude_path=None):
    """
    Discovers the true base directory and locates the original base heightmap file
    for tile (tile_x, tile_y), even if the tile has been overridden by detail maps.
    """
    candidate_dirs = []
    if getattr(props, 'folder_path', ''):
        bp = bpy.path.abspath(props.folder_path)
        if os.path.isdir(bp):
            if not exclude_path or os.path.abspath(bp) != os.path.abspath(os.path.dirname(exclude_path)):
                candidate_dirs.append(bp)

    for obj in context.scene.objects:
        if obj.get("is_gaea_tile") and not obj.get("is_detail_tile"):
            disp = obj.modifiers.get("Gaea_Displacement")
            if disp and disp.texture and getattr(disp.texture, 'image', None) and disp.texture.image.filepath:
                n_p = bpy.path.abspath(disp.texture.image.filepath)
                if os.path.isfile(n_p):
                    ndir = os.path.dirname(n_p)
                    if ndir not in candidate_dirs:
                        if not exclude_path or os.path.abspath(ndir) != os.path.abspath(os.path.dirname(exclude_path)):
                            candidate_dirs.append(ndir)

    for c_dir in candidate_dirs:
        try:
            for f in os.listdir(c_dir):
                cat, _ = classify_file(f)
                if cat == 'height':
                    tx, ty, _ = extract_tile_coords(f)
                    if tx == tile_x and ty == tile_y:
                        full_p = os.path.join(c_dir, f)
                        if os.path.isfile(full_p):
                            if not exclude_path or os.path.abspath(full_p) != os.path.abspath(exclude_path):
                                return full_p
        except Exception:
            pass

    # Check active tile object if it has not been flagged as detail tile yet
    target_name = f"Gaea_Tile_x{tile_x}_y{tile_y}"
    tile_obj = bpy.data.objects.get(target_name)
    if tile_obj and not tile_obj.get("is_detail_tile"):
        disp = tile_obj.modifiers.get("Gaea_Displacement")
        if disp and disp.texture and hasattr(disp.texture, 'image') and disp.texture.image:
            p = bpy.path.abspath(disp.texture.image.filepath)
            if os.path.isfile(p):
                if not exclude_path or os.path.abspath(p) != os.path.abspath(exclude_path):
                    return p

    # Check tile_data_json
    if getattr(props, 'tile_data_json', ''):
        try:
            t_json = json.loads(props.tile_data_json)
            key = f"{tile_x}_{tile_y}"
            cand = t_json.get(key, {}).get('height')
            if cand and os.path.isfile(cand):
                if not exclude_path or os.path.abspath(cand) != os.path.abspath(exclude_path):
                    return cand
        except Exception:
            pass

    return None


def auto_calibrate_detail_tile(context, props, tile_x, tile_y, detail_maps, orig_height_path=None):
    """
    Analyzes the detail heightmap against the base tile's heightmap to automatically solve:
      - height_scale: compensates for local elevation range compression in Gaea Region exports
      - mid_level: compensates for base ground offset
      - flip_y: detects inverted vertical orientation (e.g. Region builds)

    Returns:
      (scale: float, mid_level: float, flip_y: bool, info_msg: str)
    """
    detail_h_path = detail_maps.get('height')
    if not detail_h_path or not os.path.isfile(detail_h_path):
        return 1.0, 0.0, False, "No detail heightmap found for calibration."

    # Find original heightmap path if not passed explicitly
    if not orig_height_path or not os.path.isfile(orig_height_path):
        orig_height_path = find_base_tile_height_path(context, props, tile_x, tile_y, exclude_path=detail_h_path)

    detail_folder = os.path.dirname(detail_h_path)
    is_region_build = False
    for rep_name in ('report.txt', 'report.json'):
        rep_p = os.path.join(detail_folder, rep_name)
        if os.path.isfile(rep_p):
            try:
                with open(rep_p, 'r', encoding='utf-8', errors='ignore') as f:
                    if 'Region' in f.read():
                        is_region_build = True
                        break
            except Exception:
                pass

    if not orig_height_path or not os.path.isfile(orig_height_path):
        flip_y = is_region_build
        msg = f"Detail tile ({tile_x}, {tile_y}): Base heightmap not found. " + ("Region build detected (Flip Y enabled)." if flip_y else "Using standard settings.")
        return 1.0, 0.0, flip_y, msg

    img_orig = None
    img_det = None
    try:
        try:
            import numpy as np
            has_numpy = True
        except ImportError:
            has_numpy = False

        img_orig = bpy.data.images.load(orig_height_path)
        img_det = bpy.data.images.load(detail_h_path)

        if has_numpy:
            pix_orig = np.array(img_orig.pixels[:])[0::4]
            pix_det = np.array(img_det.pixels[:])[0::4]

            min_orig, max_orig = float(pix_orig.min()), float(pix_orig.max())
            min_det, max_det = float(pix_det.min()), float(pix_det.max())
        else:
            p_o = img_orig.pixels[0::4]
            p_d = img_det.pixels[0::4]
            min_orig, max_orig = min(p_o), max(p_o)
            min_det, max_det = min(p_d), max(p_d)

        range_orig = max_orig - min_orig
        range_det = max_det - min_det

        scale = 1.0
        mid_level = 0.0

        if range_det > 1e-6 and range_orig > 1e-6:
            ratio = range_orig / range_det
            if abs(ratio - 1.0) > 0.05:
                scale = ratio
                mid_level = min_det - (min_orig / scale)

        flip_y = is_region_build
        if has_numpy:
            w_o, h_o = img_orig.size
            w_d, h_d = img_det.size
            grid_size = min(32, min(w_o, h_o, w_d, h_d))
            if grid_size >= 4:
                p_o_2d = pix_orig.reshape((h_o, w_o))
                p_d_2d = pix_det.reshape((h_d, w_d))

                idx_o_y = np.linspace(0, h_o - 1, grid_size, dtype=int)
                idx_o_x = np.linspace(0, w_o - 1, grid_size, dtype=int)
                idx_d_y = np.linspace(0, h_d - 1, grid_size, dtype=int)
                idx_d_x = np.linspace(0, w_d - 1, grid_size, dtype=int)

                sub_o = p_o_2d[np.ix_(idx_o_y, idx_o_x)].flatten()
                sub_d_grid = p_d_2d[np.ix_(idx_d_y, idx_d_x)]
                sub_d = sub_d_grid.flatten()
                sub_d_flip = np.flipud(sub_d_grid).flatten()

                std_o = float(np.std(sub_o))
                std_d = float(np.std(sub_d))

                if std_o > 1e-6 and std_d > 1e-6:
                    c_norm = float(np.corrcoef(sub_o, sub_d)[0, 1])
                    c_flip = float(np.corrcoef(sub_o, sub_d_flip)[0, 1])

                    if c_flip > c_norm + 0.1 or (is_region_build and c_flip >= c_norm):
                        flip_y = True
                    elif c_norm > c_flip + 0.1:
                        flip_y = False

        msg = (
            f"Auto-matched Tile ({tile_x}, {tile_y}): "
            f"Scale={scale:.3f}x, Midlevel={mid_level:.4f}, Flip Y={flip_y}"
        )
        return scale, mid_level, flip_y, msg

    except Exception as e:
        msg = f"Auto-calibration warning: {e}. Using default scale=1.0."
        return 1.0, 0.0, is_region_build, msg

    finally:
        if img_orig and img_orig.users == 0:
            try:
                bpy.data.images.remove(img_orig)
            except Exception:
                pass
        if img_det and img_det.users == 0:
            try:
                bpy.data.images.remove(img_det)
            except Exception:
                pass


def create_tiled_terrain(context, props, tiles_data=None):
    """
    Creates a full tiled terrain in Blender composed of coordinate-aligned
    grid planes parented to a root Empty object.

    The overall terrain spans exactly props.terrain_width (X) and props.terrain_length (Y).
    Each tile is sized to:
        tile_width = props.terrain_width / props.tile_cols
        tile_length = props.terrain_length / props.tile_rows
    Elevation (Z) displacement strength = props.terrain_height.
    """
    if tiles_data is None:
        raw_json = getattr(props, 'tile_data_json', '')
        if raw_json:
            try:
                tiles_data = json.loads(raw_json)
            except Exception:
                tiles_data = {}
        else:
            tiles_data = {}

    nx = max(1, props.tile_cols)
    ny = max(1, props.tile_rows)
    total_w = props.terrain_width
    total_l = props.terrain_length
    total_h = props.terrain_height
    origin_type = props.terrain_origin
    flip_y = props.tile_flip_y

    tile_w = total_w / nx
    tile_l = total_l / ny

    # Proportionally downscaled subdivision values for each tile
    eff_base_subdiv, eff_subdiv_vp, eff_subdiv_ren = get_effective_tile_subdivisions(props)

    # Base coordinates for the total terrain bounds
    if origin_type == 'CENTER':
        base_x = -total_w / 2.0
        base_y = -total_l / 2.0
    else:  # CORNER
        base_x = 0.0
        base_y = 0.0

    # Dedicated Collection
    coll_name = f"Gaea_Terrain_{nx}x{ny}"
    target_coll = bpy.data.collections.get(coll_name)
    if not target_coll:
        target_coll = bpy.data.collections.new(coll_name)
        context.scene.collection.children.link(target_coll)

    # Root Empty Object
    root_name = f"Gaea_Terrain_Tiled_{nx}x{ny}"
    root_obj = bpy.data.objects.new(root_name, None)
    root_obj.empty_display_type = 'PLAIN_AXES'
    root_obj.empty_display_size = max(total_w, total_l) * 0.05
    root_obj.location = (0.0, 0.0, 0.0)
    root_obj["is_gaea_terrain"] = True
    root_obj["gaea_type"] = f"Tiled Terrain ({nx}x{ny} tiles)"
    root_obj["is_tiled"] = True
    root_obj["tile_cols"] = nx
    root_obj["tile_rows"] = ny
    root_obj["tile_grid_info"] = f"{nx}x{ny} tiles"
    root_obj["terrain_width"] = total_w
    root_obj["terrain_length"] = total_l
    root_obj["terrain_height"] = total_h
    root_obj["tile_flip_y"] = flip_y

    target_coll.objects.link(root_obj)

    created_tiles = []

    for iy in range(ny):
        for ix in range(nx):
            center_x = base_x + (ix + 0.5) * tile_w
            row_eff = (ny - 1) - iy if flip_y else iy
            center_y = base_y + (row_eff + 0.5) * tile_l

            tile_key = f"{ix}_{iy}"
            t_info = dict(tiles_data.get(tile_key) or tiles_data.get((ix, iy), {}))

            # Check if this tile has detail high-res override
            is_detail_tile = (
                getattr(props, 'enable_tile_override', False)
                and getattr(props, 'detail_folder_path', '')
                and ix == getattr(props, 'detail_tile_x', 0)
                and iy == getattr(props, 'detail_tile_y', 0)
            )

            tile_subdiv_vp = eff_subdiv_vp
            tile_subdiv_ren = eff_subdiv_ren

            if is_detail_tile:
                detail_maps = scan_detail_folder(props.detail_folder_path, target_x=ix, target_y=iy)
                keep_orig_h = getattr(props, 'detail_keep_original_height', False)
                if detail_maps:
                    orig_h_cand = t_info.get('height')
                    if getattr(props, 'detail_auto_match', True):
                        cal_s, cal_m, cal_f, _ = auto_calibrate_detail_tile(
                            context, props, ix, iy, detail_maps, orig_height_path=orig_h_cand
                        )
                        props.detail_height_scale = round(cal_s, 3)
                        props.detail_mid_level = round(cal_m, 4)
                        props.detail_flip_y = cal_f
                        props.detail_invert_height = False

                    if keep_orig_h:
                        orig_h_saved = t_info.get('height')
                        t_info.update(detail_maps)
                        if orig_h_saved:
                            t_info['height'] = orig_h_saved
                    else:
                        t_info.update(detail_maps)

                boost = getattr(props, 'detail_subdiv_boost', 0)
                tile_subdiv_vp = eff_subdiv_vp + boost
                tile_subdiv_ren = eff_subdiv_ren + boost

                if keep_orig_h:
                    tile_terrain_height = total_h
                    tile_mid_level = 0.0
                    tile_flip_y_mesh = False
                    tile_flip_y_mat = getattr(props, 'detail_flip_y', False)
                else:
                    h_scale = getattr(props, 'detail_height_scale', 1.0)
                    if getattr(props, 'detail_invert_height', False):
                        h_scale = -h_scale
                    tile_terrain_height = total_h * h_scale
                    tile_mid_level = getattr(props, 'detail_mid_level', 0.0)
                    tile_flip_y_mesh = getattr(props, 'detail_flip_y', False)
                    tile_flip_y_mat = False
            else:
                tile_terrain_height = total_h
                tile_mid_level = 0.0
                tile_flip_y_mesh = False
                tile_flip_y_mat = False

            tile_name = f"Gaea_Tile_x{ix}_y{iy}"
            tile_mesh = create_tile_plane_mesh(
                name=f"{tile_name}_Mesh",
                width=tile_w,
                length=tile_l,
                subdivisions=eff_base_subdiv,
                smooth=props.smooth_shading
            )

            tile_obj = bpy.data.objects.new(tile_name, tile_mesh)
            tile_obj.location = (center_x, center_y, 0.0)
            tile_obj.parent = root_obj
            tile_obj["is_gaea_terrain"] = True
            tile_obj["is_gaea_tile"] = True
            tile_obj["tile_x"] = ix
            tile_obj["tile_y"] = iy
            tile_obj["is_detail_tile"] = is_detail_tile
            tile_obj["gaea_type"] = "Tiled Heightmap Plane"

            if is_detail_tile:
                set_tile_uv_orientation(tile_obj, flip_y=tile_flip_y_mesh)

            target_coll.objects.link(tile_obj)
            created_tiles.append(tile_obj)

            # Setup displacement modifier if heightmap exists
            height_path = t_info.get('height')
            if height_path and os.path.isfile(height_path):
                disp_mod = setup_height_displacement(
                    obj=tile_obj,
                    height_image_path=height_path,
                    terrain_height=tile_terrain_height,
                    subdiv_viewport=tile_subdiv_vp,
                    subdiv_render=tile_subdiv_ren,
                    subdiv_type=props.subdiv_type
                )
                if disp_mod:
                    disp_mod.mid_level = tile_mid_level
                    disp_mod.texture_coords = 'UV'
                    disp_mod.uv_layer = 'UVMap'
                    if disp_mod.texture:
                        disp_mod.texture.use_flip_axis = False

            # Build and assign PBR material for this tile
            tile_maps = {
                'height': height_path if (height_path and os.path.isfile(height_path)) else None,
                'normal': t_info.get('normal'),
                'albedo': t_info.get('albedo'),
                'roughness': t_info.get('roughness'),
                'ao': t_info.get('ao'),
                'masks': list(t_info.get('masks', {}).values()) if isinstance(t_info.get('masks'), dict) else t_info.get('masks', []),
            }

            build_terrain_material(
                obj=tile_obj,
                detected_maps=tile_maps,
                terrain_height=tile_terrain_height,
                use_cycles_displacement=props.use_cycles_adaptive,
                mix_ao=props.mix_ambient_occlusion,
                ao_factor=props.ao_factor,
                default_roughness=props.default_roughness,
                flip_y=tile_flip_y_mat
            )

    # Set selection
    bpy.ops.object.select_all(action='DESELECT')
    root_obj.select_set(True)
    for t_obj in created_tiles:
        t_obj.select_set(True)
    context.view_layer.objects.active = root_obj

    return root_obj


def apply_detail_to_tile(context, props, tile_x, tile_y, detail_folder_path, subdiv_boost=1,
                         height_scale=1.0, invert_height=False, mid_level=0.0, flip_y=False,
                         auto_match=True, keep_height=False):
    """
    Applies high-resolution replacement maps from detail_folder_path to the specified
    tile (tile_x, tile_y) on an existing tiled terrain in the scene.
    If keep_height is True, preserves the original base height displacement and replaces
    only surface textures (Albedo, Normal, Roughness, AO, Masks) with flip_y handled in shader.
    Also updates props.tile_data_json so the state persists.

    Returns:
      (success: bool, message: str)
    """
    folder_abs = bpy.path.abspath(detail_folder_path)
    if not folder_abs or not os.path.isdir(folder_abs):
        return False, f"Detail folder does not exist: '{detail_folder_path}'"

    detail_maps = scan_detail_folder(folder_abs, target_x=tile_x, target_y=tile_y)
    if not detail_maps:
        return False, f"No valid terrain map images found in '{detail_folder_path}'"

    # Auto-calibrate if requested
    cal_msg = ""
    if auto_match:
        cal_scale, cal_mid, cal_flip, cal_msg = auto_calibrate_detail_tile(
            context, props, tile_x, tile_y, detail_maps
        )
        props.detail_height_scale = round(cal_scale, 3)
        props.detail_mid_level = round(cal_mid, 4)
        props.detail_flip_y = cal_flip
        props.detail_invert_height = False
        height_scale = props.detail_height_scale
        mid_level = props.detail_mid_level
        flip_y = props.detail_flip_y
        invert_height = False

    # Find the target tile object in the scene
    target_name = f"Gaea_Tile_x{tile_x}_y{tile_y}"
    tile_obj = bpy.data.objects.get(target_name)

    if not tile_obj:
        for obj in context.scene.objects:
            if obj.get("is_gaea_tile") and obj.get("tile_x") == tile_x and obj.get("tile_y") == tile_y:
                tile_obj = obj
                break

    # Discover original base heightmap if keep_height is requested
    orig_base_height = None
    if keep_height:
        props.detail_keep_original_height = True
        orig_base_height = find_base_tile_height_path(
            context, props, tile_x, tile_y, exclude_path=detail_maps.get('height')
        )
    else:
        props.detail_keep_original_height = False

    # Update serialized tile data JSON
    tiles_data = {}
    if getattr(props, 'tile_data_json', ''):
        try:
            tiles_data = json.loads(props.tile_data_json)
        except Exception:
            tiles_data = {}

    tile_key = f"{tile_x}_{tile_y}"
    current_entry = dict(tiles_data.get(tile_key, {}))

    if keep_height:
        # Preserve original base height path in JSON if known
        saved_h = orig_base_height or current_entry.get('height')
        current_entry.update(detail_maps)
        if saved_h:
            current_entry['height'] = saved_h
    else:
        current_entry.update(detail_maps)

    tiles_data[tile_key] = current_entry
    props.tile_data_json = json.dumps(tiles_data)

    if not tile_obj:
        action_desc = "Detail textures (base height preserved)" if keep_height else "Detail maps"
        return True, f"{action_desc} registered for Tile ({tile_x}, {tile_y}). Will be used on next import. {cal_msg}"

    # Track old images used on this tile so unreferenced images can be purged from memory
    old_images = set()
    disp_prev = tile_obj.modifiers.get("Gaea_Displacement")
    if disp_prev and disp_prev.texture and hasattr(disp_prev.texture, 'image') and disp_prev.texture.image:
        old_images.add(disp_prev.texture.image)
    if tile_obj.data.materials:
        for mat in tile_obj.data.materials:
            if mat and mat.use_nodes:
                for n in mat.node_tree.nodes:
                    if n.type == 'TEX_IMAGE' and getattr(n, 'image', None):
                        old_images.add(n.image)

    # Compute target subdivision levels idempotently from the terrain's base tile settings
    eff_base, eff_vp, eff_ren = get_effective_tile_subdivisions(props)
    base_vp = eff_vp if props.auto_scale_tiled_subdiv else props.subdiv_levels_viewport
    base_ren = eff_ren if props.auto_scale_tiled_subdiv else props.subdiv_levels_render
    target_vp = min(max(base_vp + subdiv_boost, 0), 6)
    target_ren = min(max(base_ren + subdiv_boost, 0), 8)

    if keep_height:
        # Keep original height displacement and un-flipped mesh UV orientation
        set_tile_uv_orientation(tile_obj, flip_y=False)

        # Restore or update base displacement
        h_to_use = orig_base_height or current_entry.get('height')
        if h_to_use and os.path.isfile(h_to_use):
            disp_mod = setup_height_displacement(
                obj=tile_obj,
                height_image_path=h_to_use,
                terrain_height=props.terrain_height,
                subdiv_viewport=target_vp,
                subdiv_render=target_ren,
                subdiv_type=props.subdiv_type
            )
            if disp_mod:
                disp_mod.mid_level = 0.0
                disp_mod.texture_coords = 'UV'
                disp_mod.uv_layer = 'UVMap'
                if disp_mod.texture:
                    disp_mod.texture.use_flip_axis = False
        else:
            if disp_prev:
                disp_prev.strength = props.terrain_height
                disp_prev.mid_level = 0.0
            subsurf = tile_obj.modifiers.get("Gaea_Subdivision")
            if subsurf:
                subsurf.levels = target_vp
                subsurf.render_levels = target_ren

        # Update / Rebuild PBR Material with detail textures, mapping flipped via shader node if flip_y
        updated_maps = {
            'height': h_to_use,
            'normal': detail_maps.get('normal') or current_entry.get('normal'),
            'albedo': detail_maps.get('albedo') or current_entry.get('albedo'),
            'roughness': detail_maps.get('roughness') or current_entry.get('roughness'),
            'ao': detail_maps.get('ao') or current_entry.get('ao'),
            'masks': detail_maps.get('masks') or (list(current_entry.get('masks', {}).values()) if isinstance(current_entry.get('masks'), dict) else current_entry.get('masks', [])),
        }

        build_terrain_material(
            obj=tile_obj,
            detected_maps=updated_maps,
            terrain_height=props.terrain_height,
            use_cycles_displacement=props.use_cycles_adaptive,
            mix_ao=props.mix_ambient_occlusion,
            ao_factor=props.ao_factor,
            default_roughness=props.default_roughness,
            flip_y=flip_y
        )
    else:
        # Compute effective displacement strength with scale and inversion
        scale_mult = height_scale if not invert_height else -height_scale
        eff_height = props.terrain_height * scale_mult

        # Ensure tile mesh UV orientation matches flip_y
        set_tile_uv_orientation(tile_obj, flip_y=flip_y)

        # Update or setup Displacement & Subdivision cleanly
        height_path = detail_maps.get('height')
        if height_path and os.path.isfile(height_path):
            disp_mod = setup_height_displacement(
                obj=tile_obj,
                height_image_path=height_path,
                terrain_height=eff_height,
                subdiv_viewport=target_vp,
                subdiv_render=target_ren,
                subdiv_type=props.subdiv_type
            )
            if disp_mod:
                disp_mod.mid_level = mid_level
                disp_mod.texture_coords = 'UV'
                disp_mod.uv_layer = 'UVMap'
                if disp_mod.texture:
                    disp_mod.texture.use_flip_axis = False
        else:
            subsurf = tile_obj.modifiers.get("Gaea_Subdivision")
            if subsurf:
                subsurf.levels = target_vp
                subsurf.render_levels = target_ren

        # Update / Rebuild PBR Material
        updated_maps = {
            'height': height_path or current_entry.get('height'),
            'normal': detail_maps.get('normal') or current_entry.get('normal'),
            'albedo': detail_maps.get('albedo') or current_entry.get('albedo'),
            'roughness': detail_maps.get('roughness') or current_entry.get('roughness'),
            'ao': detail_maps.get('ao') or current_entry.get('ao'),
            'masks': detail_maps.get('masks') or (list(current_entry.get('masks', {}).values()) if isinstance(current_entry.get('masks'), dict) else current_entry.get('masks', [])),
        }

        build_terrain_material(
            obj=tile_obj,
            detected_maps=updated_maps,
            terrain_height=eff_height,
            use_cycles_displacement=props.use_cycles_adaptive,
            mix_ao=props.mix_ambient_occlusion,
            ao_factor=props.ao_factor,
            default_roughness=props.default_roughness,
            flip_y=False
        )

    # Purge any old image datablocks that are no longer referenced anywhere to free RAM
    for img in old_images:
        if img and img.users == 0:
            try:
                bpy.data.images.remove(img)
            except Exception:
                pass

    tile_obj["is_detail_tile"] = True
    tile_obj["detail_keep_height"] = keep_height

    status_extra = f" [{cal_msg}]" if cal_msg else ""
    if keep_height:
        return True, f"Successfully replaced textures on Tile ({tile_x}, {tile_y}) keeping original base height displacement.{status_extra}"
    else:
        return True, f"Successfully applied high-res detail maps to Tile ({tile_x}, {tile_y}) '{tile_obj.name}'{status_extra}"


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


def ensure_mesh_uv_map(obj, force_planar=False):
    """
    Ensures the mesh object has a valid UV map.
    If no UV map exists (or force_planar is True, or existing UV map is empty/all-zero),
    generates a normalized [0, 1] top-down planar UV map matching Gaea's orthographic coordinate space.
    """
    if not obj or obj.type != 'MESH' or not obj.data:
        return False

    mesh = obj.data
    needs_uv = False

    if len(mesh.uv_layers) == 0:
        needs_uv = True
    elif force_planar:
        needs_uv = True
    else:
        uv_layer = mesh.uv_layers.active or mesh.uv_layers[0]
        if len(uv_layer.data) == 0:
            needs_uv = True
        else:
            # Check if all sampled UV coordinates are near (0, 0)
            all_zero = True
            for i in range(min(50, len(uv_layer.data))):
                u, v = uv_layer.data[i].uv
                if abs(u) > 1e-5 or abs(v) > 1e-5:
                    all_zero = False
                    break
            if all_zero:
                needs_uv = True

    if needs_uv:
        if len(mesh.vertices) == 0 or len(mesh.loops) == 0:
            return False

        uv_layer = mesh.uv_layers.get("UVMap")
        if not uv_layer:
            uv_layer = mesh.uv_layers.new(name="UVMap")
        mesh.uv_layers.active = uv_layer

        try:
            import numpy as np

            # Fast vectorized UV calculation using numpy
            num_verts = len(mesh.vertices)
            coords = np.empty(num_verts * 3, dtype=np.float32)
            mesh.vertices.foreach_get('co', coords)
            coords = coords.reshape((-1, 3))

            # Transform to world space
            mat = np.array(obj.matrix_world, dtype=np.float32)
            coords_homo = np.hstack([coords, np.ones((num_verts, 1), dtype=np.float32)])
            world_coords = (coords_homo @ mat.T)[:, :3]

            min_x = float(world_coords[:, 0].min())
            max_x = float(world_coords[:, 0].max())
            min_y = float(world_coords[:, 1].min())
            max_y = float(world_coords[:, 1].max())

            w = max_x - min_x if max_x - min_x > 1e-5 else 1.0
            l = max_y - min_y if max_y - min_y > 1e-5 else 1.0

            vert_u = (world_coords[:, 0] - min_x) / w
            vert_v = (world_coords[:, 1] - min_y) / l
            vert_uvs = np.column_stack([vert_u, vert_v]).astype(np.float32)

            # Map per-vertex UVs to all mesh loops
            loop_vert_idx = np.empty(len(mesh.loops), dtype=np.int32)
            mesh.loops.foreach_get('vertex_index', loop_vert_idx)
            loop_uvs = vert_uvs[loop_vert_idx].ravel()

            uv_layer.data.foreach_set('uv', loop_uvs)

        except Exception:
            # Pure Python fallback
            world_mat = obj.matrix_world
            min_x = min((world_mat @ v.co).x for v in mesh.vertices)
            max_x = max((world_mat @ v.co).x for v in mesh.vertices)
            min_y = min((world_mat @ v.co).y for v in mesh.vertices)
            max_y = max((world_mat @ v.co).y for v in mesh.vertices)

            width = max_x - min_x if max_x - min_x > 1e-5 else 1.0
            length = max_y - min_y if max_y - min_y > 1e-5 else 1.0

            uv_data = uv_layer.data
            for poly in mesh.polygons:
                for loop_idx in poly.loop_indices:
                    v_idx = mesh.loops[loop_idx].vertex_index
                    world_co = world_mat @ mesh.vertices[v_idx].co
                    u = (world_co.x - min_x) / width
                    v = (world_co.y - min_y) / length
                    uv_data[loop_idx].uv = (u, v)

        mesh.update()
        return True

    # Ensure active UV layer is set
    if not mesh.uv_layers.active:
        mesh.uv_layers.active = mesh.uv_layers[0]
    return False


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
                           default_roughness=1.0, flip_y=False):
    """
    Builds a complete PBR node network for the terrain object.
    Supports Albedo (sRGB color map), Roughness (with configurable default value),
    Normal Map, AO mixing, Height (Cycles displacement), and auxiliary data masks.
    If flip_y is True, routes texture coordinates through a Mapping node (Scale Y = -1, Loc Y = 1).
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

    # Ensure the object has a valid UV map
    ensure_mesh_uv_map(obj)

    # Base coordinates
    pos_x = -800
    pos_y = 300

    # Output & Principled BSDF
    node_out = nodes.new(type='ShaderNodeOutputMaterial')
    node_out.location = (400, 200)

    node_bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
    node_bsdf.location = (50, 200)
    links.new(node_bsdf.outputs['BSDF'], node_out.inputs['Surface'])

    # Texture Coordinate Node for explicit UV mapping
    node_texcoord = nodes.new(type='ShaderNodeTexCoord')
    node_texcoord.location = (pos_x - 300, 300)

    uv_out = node_texcoord.outputs['UV']
    if flip_y:
        node_mapping = nodes.new(type='ShaderNodeMapping')
        node_mapping.location = (pos_x - 150, 300)
        node_mapping.inputs['Location'].default_value = (0.0, 1.0, 0.0)
        node_mapping.inputs['Scale'].default_value = (1.0, -1.0, 1.0)
        links.new(node_texcoord.outputs['UV'], node_mapping.inputs['Vector'])
        uv_out = node_mapping.outputs['Vector']

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
            links.new(uv_out, node_albedo.inputs['Vector'])

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
            links.new(uv_out, node_ao.inputs['Vector'])

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
            links.new(uv_out, node_rough.inputs['Vector'])
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
            links.new(uv_out, node_norm_tex.inputs['Vector'])

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
            links.new(uv_out, node_height_tex.inputs['Vector'])

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
            links.new(uv_out, node_mask.inputs['Vector'])
            aux_y -= 250

    # Assign material to object
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

    return mat


def configure_scene_and_viewport(scene=None, min_clip_end=100000.0, set_material_shading=True):
    """
    Ensure scene units are set to Metric (Meters), update 3D Viewport clip_end
    (and scene camera clip_end) to at least min_clip_end (default 100,000 meters),
    and set viewport shading to MATERIAL preview so textures are immediately visible.
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
            if set_material_shading and hasattr(space_data, 'shading'):
                space_data.shading.type = 'MATERIAL'
    except Exception:
        pass

    # 3. Update all 3D Viewport spaces across all screens and windows
    try:
        for screen in bpy.data.screens:
            for area in screen.areas:
                if area.type == 'VIEW_3D':
                    for space in area.spaces:
                        if space.type == 'VIEW_3D':
                            if space.clip_end < min_clip_end:
                                space.clip_end = min_clip_end
                            if set_material_shading and hasattr(space, 'shading'):
                                space.shading.type = 'MATERIAL'
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
    Check if an object is an imported Gaea terrain mesh, generated heightmap plane,
    or a tiled terrain root empty or tile mesh.
    """
    if not obj:
        return False

    # Check root empty for tiled terrain
    if obj.type == 'EMPTY' and (obj.get("is_gaea_terrain") or obj.get("is_tiled")):
        return True

    if obj.type != 'MESH':
        return False

    # Check custom tags
    if obj.get("is_gaea_terrain") or obj.get("is_gaea_tile"):
        return True

    # Check for Gaea modifiers
    if "Gaea_Displacement" in obj.modifiers or "Gaea_Subdivision" in obj.modifiers:
        return True

    # Check object name
    if obj.name.startswith("Gaea_Terrain") or obj.name.startswith("Gaea_Tile"):
        return True

    # Check assigned materials
    if obj.data.materials and any(m and m.name.startswith("M_Gaea") for m in obj.data.materials):
        return True

    return False


def update_terrain_maps(obj, detected_maps, terrain_height=500.0,
                        subdiv_viewport=4, subdiv_render=6, subdiv_type='SIMPLE',
                        use_cycles_disp=False, mix_ao=True, ao_factor=0.8,
                        default_roughness=1.0, tile_data_json=""):
    """
    Updates the heightmap displacement modifier (if present) and rebuilds/updates
    the PBR material network on an existing Gaea terrain object using the newly selected maps.
    Supports both single-mesh terrains and tiled terrain systems.
    """
    if not is_gaea_terrain(obj):
        return False

    # Check if this object belongs to a tiled terrain system
    is_tiled_root = (obj.type == 'EMPTY' and (obj.get("is_tiled") or obj.get("is_gaea_terrain")))
    is_tile_child = (obj.type == 'MESH' and obj.get("is_gaea_tile") and obj.parent and obj.parent.get("is_tiled"))

    if is_tiled_root or is_tile_child:
        root_obj = obj if is_tiled_root else obj.parent
        tiles = [child for child in root_obj.children if child.type == 'MESH' and child.get("is_gaea_tile")]

        # Parse tile data
        tiles_data = {}
        if tile_data_json:
            try:
                tiles_data = json.loads(tile_data_json)
            except Exception:
                tiles_data = {}

        for tile in tiles:
            ix = tile.get("tile_x", 0)
            iy = tile.get("tile_y", 0)
            tile_key = f"{ix}_{iy}"
            t_info = tiles_data.get(tile_key, {})
            tile_height_path = t_info.get('height') or detected_maps.get('height')

            # Update displacement
            disp_mod = tile.modifiers.get("Gaea_Displacement")
            if disp_mod and tile_height_path and os.path.exists(tile_height_path):
                img = load_image_safely(tile_height_path, colorspace='Non-Color')
                if img:
                    tex_name = f"Gaea_Height_{tile.name}"
                    tex = bpy.data.textures.get(tex_name)
                    if not tex:
                        tex = bpy.data.textures.new(name=tex_name, type='IMAGE')
                    tex.image = img
                    tex.extension = 'EXTEND'
                    disp_mod.texture = tex
                    disp_mod.strength = terrain_height

            subsurf_mod = tile.modifiers.get("Gaea_Subdivision")
            if subsurf_mod:
                subsurf_mod.levels = subdiv_viewport
                subsurf_mod.render_levels = subdiv_render
                subsurf_mod.subdivision_type = subdiv_type

            # Tile maps
            t_maps = {
                'height': tile_height_path if (tile_height_path and os.path.isfile(tile_height_path)) else None,
                'normal': t_info.get('normal') or detected_maps.get('normal'),
                'albedo': t_info.get('albedo') or detected_maps.get('albedo'),
                'roughness': t_info.get('roughness') or detected_maps.get('roughness'),
                'ao': t_info.get('ao') or detected_maps.get('ao'),
                'masks': list(t_info.get('masks', {}).values()) if isinstance(t_info.get('masks'), dict) else detected_maps.get('masks', []),
            }
            build_terrain_material(
                obj=tile,
                detected_maps=t_maps,
                terrain_height=terrain_height,
                use_cycles_displacement=use_cycles_disp,
                mix_ao=mix_ao,
                ao_factor=ao_factor,
                default_roughness=default_roughness
            )
        return True

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


