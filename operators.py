"""
Operator definitions for CEB_Gaea2Blender add-on.
Implements folder scanning, terrain generation/import, mesh scaling,
and material assignment.
"""

import os
import json
import bpy
from . import utils
from . import properties


class GAEA_OT_scan_folder(bpy.types.Operator):
    """Scan the selected folder for QuadSpinner Gaea generated files"""
    bl_idname = "gaea.scan_folder"
    bl_label = "Scan Gaea Output Folder"
    bl_description = "Analyze directory and identify meshes, heightmaps, normal maps, and PBR textures"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        properties.clear_folder_cache()
        props = context.scene.gaea_terrain_props
        folder = bpy.path.abspath(props.folder_path)

        if not folder or not os.path.isdir(folder):
            self.report({'ERROR'}, "Please specify a valid folder path first.")
            return {'CANCELLED'}

        results = utils.scan_gaea_folder(folder)

        # Clear previous slots & correspondence items
        props.map_items.clear()
        props.detected_mesh_path = ""
        props.detected_height_path = ""
        props.detected_normal_path = ""
        props.detected_albedo_path = ""
        props.detected_roughness_path = ""
        props.detected_ao_path = ""

        # Check if folder contains tiled terrain build
        is_tiled = results.get('is_tiled', False)
        props.is_tiled = is_tiled
        if is_tiled:
            props.tile_cols = results.get('tile_cols', 1)
            props.tile_rows = results.get('tile_rows', 1)
            props.tile_total_count = results.get('tile_total_count', 1)
            props.tile_grid_info = results.get('tile_grid_info', "")
            props.tile_data_json = json.dumps(results.get('tiles', {}))
            props.use_tiling = True
        else:
            props.tile_cols = 1
            props.tile_rows = 1
            props.tile_total_count = 1
            props.tile_grid_info = ""
            props.tile_data_json = ""
            props.use_tiling = False

        def add_corr_item(category, slot_name, paths, destination, icon_name, prop_name=None):
            if paths:
                primary = paths[0]
                if prop_name:
                    setattr(props, prop_name, primary)
                item = props.map_items.add()
                item.category = category
                item.slot_name = f"{slot_name} ({props.tile_grid_info})" if is_tiled else slot_name
                item.filename = os.path.basename(primary)
                item.filepath = primary
                item.destination = f"{destination} per Tile" if is_tiled else destination
                item.icon_name = icon_name
                item.is_assigned = True
                try:
                    item.selected_file = os.path.basename(primary)
                except Exception:
                    pass

                # If NOT tiled and multiple files exist for this category, list them as alternatives
                if not is_tiled:
                    for idx, extra_p in enumerate(paths[1:], start=2):
                        item_extra = props.map_items.add()
                        item_extra.category = category
                        item_extra.slot_name = f"{slot_name} #{idx}"
                        item_extra.filename = os.path.basename(extra_p)
                        item_extra.filepath = extra_p
                        item_extra.destination = f"{destination} (Alternative)"
                        item_extra.icon_name = icon_name
                        item_extra.is_assigned = True
                        try:
                            item_extra.selected_file = os.path.basename(extra_p)
                        except Exception:
                            pass
            else:
                item = props.map_items.add()
                item.category = category
                item.slot_name = slot_name
                item.filename = "[Not Found]"
                item.filepath = ""
                item.destination = destination
                item.icon_name = icon_name
                item.is_assigned = False
                try:
                    item.selected_file = 'NONE'
                except Exception:
                    pass

        # Populate primary slots and correspondences
        add_corr_item("Height", "Heightmap", results['height'], "Displacement Modifier & Elevation (Z)", "MOD_DISPLACE", "detected_height_path")
        add_corr_item("Normal", "Normal Map", results['normal'], "Principled BSDF > Tangent Normal", "NORMALS_FACE", "detected_normal_path")
        add_corr_item("Albedo", "Albedo / Base Color", results['albedo'], "Principled BSDF > Base Color", "COLOR", "detected_albedo_path")
        add_corr_item("Roughness", "Roughness Map", results['roughness'], "Principled BSDF > Roughness", "NODE_TEXTURE", "detected_roughness_path")
        add_corr_item("AO", "Ambient Occlusion", results['ao'], "Mix Color Node (Multiply) > Base Color", "SHADING_RENDERED", "detected_ao_path")
        add_corr_item("Mesh", "Terrain Mesh", results['mesh'], "3D Viewport Geometry (Scaled)", "MESH_DATA", "detected_mesh_path")

        # Additional Masks (biomes, vegetation, slope, rocks, etc.)
        if is_tiled:
            for ch_name, ch_paths in results.get('tiled_channels', {}).items():
                if ch_name.startswith("Mask: "):
                    item = props.map_items.add()
                    item.category = "Mask"
                    item.slot_name = f"{ch_name} ({props.tile_grid_info})"
                    item.filename = os.path.basename(ch_paths[0]) if ch_paths else ""
                    item.filepath = ch_paths[0] if ch_paths else ""
                    item.destination = "Shader Graph > Material Mask Node per Tile"
                    item.icon_name = "IMAGE_RGB"
                    item.is_assigned = True
                    try:
                        item.selected_file = os.path.basename(ch_paths[0]) if ch_paths else 'NONE'
                    except Exception:
                        pass
        else:
            for mask_p in results.get('masks', []):
                item = props.map_items.add()
                base_name = os.path.splitext(os.path.basename(mask_p))[0]
                item.category = "Mask"
                item.slot_name = f"Mask: {base_name}"
                item.filename = os.path.basename(mask_p)
                item.filepath = mask_p
                item.destination = "Shader Graph > Material Mask Node"
                item.icon_name = "IMAGE_RGB"
                item.is_assigned = True
                try:
                    item.selected_file = os.path.basename(mask_p)
                except Exception:
                    pass

        # Unmatched files in folder (not automatically assigned as masks)
        for un_p in results.get('unmatched', []):
            item = props.map_items.add()
            item.category = "Unused"
            item.slot_name = "Unused File"
            item.filename = os.path.basename(un_p)
            item.filepath = un_p
            item.destination = "Not Used"
            item.icon_name = "IMAGE_DATA"
            item.is_assigned = False

        props.found_mesh_count = len(results['mesh'])
        props.found_image_count = len(results['all_images'])
        props.has_scanned = True

        # Determine initial import_mode based on detected files
        if results['height'] and results['mesh']:
            if props.import_mode not in {'HEIGHTMAP', 'MESH'}:
                props.import_mode = 'HEIGHTMAP'
        elif results['mesh']:
            props.import_mode = 'MESH'
        elif results['height']:
            props.import_mode = 'HEIGHTMAP'

        if is_tiled:
            status_msg = f"Found: {props.tile_grid_info} ({props.tile_total_count} total), {props.found_mesh_count} mesh(es), {props.found_image_count} map(s)"
        else:
            status_msg = f"Found: {props.found_mesh_count} mesh(es), {props.found_image_count} map(s)"
        props.scan_status = status_msg
        self.report({'INFO'}, f"Gaea scan complete: {status_msg}")
        return {'FINISHED'}


class GAEA_OT_clear_slots(bpy.types.Operator):
    """Clear all detected file slots"""
    bl_idname = "gaea.clear_slots"
    bl_label = "Clear File Slots"
    bl_description = "Clear all detected mesh and texture file assignments"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        properties.clear_folder_cache()
        props = context.scene.gaea_terrain_props
        props.map_items.clear()
        props.detected_mesh_path = ""
        props.detected_height_path = ""
        props.detected_normal_path = ""
        props.detected_albedo_path = ""
        props.detected_roughness_path = ""
        props.detected_ao_path = ""
        props.is_tiled = False
        props.tile_cols = 1
        props.tile_rows = 1
        props.tile_total_count = 1
        props.tile_grid_info = ""
        props.tile_data_json = ""
        props.use_tiling = False
        props.has_scanned = False
        props.scan_status = "Cleared"
        self.report({'INFO'}, "Cleared file slots.")
        return {'FINISHED'}


def _import_mesh_file(filepath):
    """Helper to import OBJ, FBX, or PLY with version-resilient operators"""
    ext = os.path.splitext(filepath)[1].lower()
    before_objects = set(bpy.data.objects)

    if ext == '.obj':
        if hasattr(bpy.ops.wm, 'obj_import'):
            bpy.ops.wm.obj_import(filepath=filepath)
        elif hasattr(bpy.ops.import_scene, 'obj'):
            bpy.ops.import_scene.obj(filepath=filepath)
        else:
            raise RuntimeError("No OBJ importer found in this Blender version.")
    elif ext == '.fbx':
        if hasattr(bpy.ops.import_scene, 'fbx'):
            bpy.ops.import_scene.fbx(filepath=filepath)
        else:
            raise RuntimeError("No FBX importer found in this Blender version.")
    elif ext == '.ply':
        if hasattr(bpy.ops.wm, 'ply_import'):
            bpy.ops.wm.ply_import(filepath=filepath)
        elif hasattr(bpy.ops.import_mesh, 'ply'):
            bpy.ops.import_mesh.ply(filepath=filepath)
        else:
            raise RuntimeError("No PLY importer found in this Blender version.")
    else:
        raise ValueError(f"Unsupported mesh format: {ext}")

    after_objects = set(bpy.data.objects)
    new_objects = [obj for obj in (after_objects - before_objects) if obj.type == 'MESH']
    return new_objects


class GAEA_OT_import_terrain(bpy.types.Operator):
    """Build terrain plane from heightmap or import mesh with configured dimensions and materials"""
    bl_idname = "gaea.import_terrain"
    bl_label = "Import & Build Gaea Terrain"
    bl_description = "Generate or import terrain, apply heightmap subdivisions, scale dimensions, and wire up PBR shaders"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.gaea_terrain_props

        # Ensure scene unit is in meters and viewport clip_end is large enough for terrain
        max_dim = max(props.terrain_width, props.terrain_length, props.terrain_height)
        needed_clip = max(100000.0, max_dim * 4.0)
        utils.configure_scene_and_viewport(context.scene, min_clip_end=needed_clip)

        # Resolve paths
        mesh_path = bpy.path.abspath(props.detected_mesh_path) if props.detected_mesh_path else ""
        height_path = bpy.path.abspath(props.detected_height_path) if props.detected_height_path else ""

        # Handle Tiled Terrain Import
        if props.is_tiled and props.use_tiling:
            tiled_obj = utils.create_tiled_terrain(context, props)
            if not tiled_obj:
                self.report({'ERROR'}, "Tiled terrain generation failed.")
                return {'CANCELLED'}

            if getattr(props, 'auto_frame_view', True):
                utils.frame_scene_view()

            self.report({'INFO'}, f"Successfully created Gaea tiled terrain '{tiled_obj.name}' ({props.tile_grid_info}, total {props.terrain_width:.0f}m x {props.terrain_length:.0f}m)")
            return {'FINISHED'}

        # Determine effective mode for single terrain
        has_mesh = bool(mesh_path and os.path.isfile(mesh_path))
        has_height = bool(height_path and os.path.isfile(height_path))

        mode = props.import_mode
        if mode == 'AUTO':
            if has_mesh and not has_height:
                mode = 'MESH'
            elif has_height:
                mode = 'HEIGHTMAP'
            else:
                self.report({'ERROR'}, "Cannot auto-detect: Neither mesh nor heightmap found. Run Scan Folder first.")
                return {'CANCELLED'}

        terrain_obj = None

        if mode == 'HEIGHTMAP':
            if not height_path or not os.path.isfile(height_path):
                self.report({'ERROR'}, "Heightmap file is missing or invalid.")
                return {'CANCELLED'}

            # 1. Create base plane grid
            terrain_obj = utils.create_terrain_grid(
                name="Gaea_Terrain",
                width=props.terrain_width,
                length=props.terrain_length,
                base_subdivisions=props.base_subdivisions,
                origin_type=props.terrain_origin,
                smooth=props.smooth_shading
            )

            # 2. Setup Subdivisions + Heightmap Displacement
            utils.setup_height_displacement(
                obj=terrain_obj,
                height_image_path=height_path,
                terrain_height=props.terrain_height,
                subdiv_viewport=props.subdiv_levels_viewport,
                subdiv_render=props.subdiv_levels_render,
                subdiv_type=props.subdiv_type
            )

        elif mode == 'MESH':
            if not mesh_path or not os.path.isfile(mesh_path):
                self.report({'ERROR'}, "Mesh file is missing or invalid.")
                return {'CANCELLED'}

            try:
                imported_objs = _import_mesh_file(mesh_path)
            except Exception as e:
                self.report({'ERROR'}, f"Failed to import mesh: {e}")
                return {'CANCELLED'}

            if not imported_objs:
                self.report({'ERROR'}, "No mesh objects found in imported file.")
                return {'CANCELLED'}

            terrain_obj = imported_objs[0]
            terrain_obj.name = "Gaea_Terrain_Mesh"
            terrain_obj["is_gaea_terrain"] = True
            terrain_obj["gaea_type"] = "Imported Mesh"

            bpy.context.view_layer.objects.active = terrain_obj
            terrain_obj.select_set(True)

            # Ensure the mesh has valid top-down UV coordinates for Gaea texture maps
            utils.ensure_mesh_uv_map(terrain_obj)

            # Note: Terrain dimension settings are ignored for imported mesh.
            # Native mesh scale and geometry from Gaea are preserved.

            if props.smooth_shading:
                for poly in terrain_obj.data.polygons:
                    poly.use_smooth = True

        if not terrain_obj:
            self.report({'ERROR'}, "Terrain generation failed.")
            return {'CANCELLED'}

        # Build & assign PBR Material
        detected_maps = {
            'height': height_path if (mode == 'HEIGHTMAP' and os.path.isfile(height_path)) else None,
            'normal': bpy.path.abspath(props.detected_normal_path) if props.detected_normal_path and os.path.isfile(bpy.path.abspath(props.detected_normal_path)) else None,
            'albedo': bpy.path.abspath(props.detected_albedo_path) if props.detected_albedo_path and os.path.isfile(bpy.path.abspath(props.detected_albedo_path)) else None,
            'roughness': bpy.path.abspath(props.detected_roughness_path) if props.detected_roughness_path and os.path.isfile(bpy.path.abspath(props.detected_roughness_path)) else None,
            'ao': bpy.path.abspath(props.detected_ao_path) if props.detected_ao_path and os.path.isfile(bpy.path.abspath(props.detected_ao_path)) else None,
            'masks': [item.filepath for item in props.map_items if item.category == 'Mask' and item.is_assigned and os.path.isfile(item.filepath)],
        }

        utils.build_terrain_material(
            obj=terrain_obj,
            detected_maps=detected_maps,
            terrain_height=props.terrain_height,
            use_cycles_displacement=props.use_cycles_adaptive,
            mix_ao=props.mix_ambient_occlusion,
            ao_factor=props.ao_factor,
            default_roughness=props.default_roughness
        )

        # Auto-frame full view of scene (equivalent of pressing Home button)
        if getattr(props, 'auto_frame_view', True):
            utils.frame_scene_view()

        self.report({'INFO'}, f"Successfully created Gaea terrain '{terrain_obj.name}' ({mode} mode)")
        return {'FINISHED'}


class GAEA_OT_setup_material(bpy.types.Operator):
    """Rebuild PBR material on active object using detected Gaea maps"""
    bl_idname = "gaea.setup_material"
    bl_label = "Rebuild Terrain Material"
    bl_description = "Apply/update Gaea shader network on the selected mesh object"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'

    def execute(self, context):
        props = context.scene.gaea_terrain_props
        obj = context.active_object

        detected_maps = {
            'height': bpy.path.abspath(props.detected_height_path) if props.detected_height_path and os.path.isfile(bpy.path.abspath(props.detected_height_path)) else None,
            'normal': bpy.path.abspath(props.detected_normal_path) if props.detected_normal_path and os.path.isfile(bpy.path.abspath(props.detected_normal_path)) else None,
            'albedo': bpy.path.abspath(props.detected_albedo_path) if props.detected_albedo_path and os.path.isfile(bpy.path.abspath(props.detected_albedo_path)) else None,
            'roughness': bpy.path.abspath(props.detected_roughness_path) if props.detected_roughness_path and os.path.isfile(bpy.path.abspath(props.detected_roughness_path)) else None,
            'ao': bpy.path.abspath(props.detected_ao_path) if props.detected_ao_path and os.path.isfile(bpy.path.abspath(props.detected_ao_path)) else None,
            'masks': [item.filepath for item in props.map_items if item.category == 'Mask' and item.is_assigned and os.path.isfile(item.filepath)],
        }

        utils.build_terrain_material(
            obj=obj,
            detected_maps=detected_maps,
            terrain_height=props.terrain_height,
            use_cycles_displacement=props.use_cycles_adaptive,
            mix_ao=props.mix_ambient_occlusion,
            ao_factor=props.ao_factor,
            default_roughness=props.default_roughness
        )

        self.report({'INFO'}, f"Material updated on '{obj.name}'.")
        return {'FINISHED'}


class GAEA_OT_update_terrain_maps(bpy.types.Operator):
    """Update displacement and PBR shader maps on the selected Gaea terrain with currently selected maps"""
    bl_idname = "gaea.update_terrain_maps"
    bl_label = "Update Maps on Selected Terrain"
    bl_description = "Apply currently selected heightmap, normal, albedo, and mask maps to the active Gaea terrain"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and utils.is_gaea_terrain(obj)

    def execute(self, context):
        props = context.scene.gaea_terrain_props
        obj = context.active_object

        if not obj or not utils.is_gaea_terrain(obj):
            self.report({'ERROR'}, "Active object is not a recognized Gaea terrain.")
            return {'CANCELLED'}

        # Ensure scene unit and clip distance
        utils.configure_scene_and_viewport(context.scene, min_clip_end=100000.0)

        # Collect currently selected maps
        detected_maps = {
            'height': bpy.path.abspath(props.detected_height_path) if props.detected_height_path and os.path.isfile(bpy.path.abspath(props.detected_height_path)) else None,
            'normal': bpy.path.abspath(props.detected_normal_path) if props.detected_normal_path and os.path.isfile(bpy.path.abspath(props.detected_normal_path)) else None,
            'albedo': bpy.path.abspath(props.detected_albedo_path) if props.detected_albedo_path and os.path.isfile(bpy.path.abspath(props.detected_albedo_path)) else None,
            'roughness': bpy.path.abspath(props.detected_roughness_path) if props.detected_roughness_path and os.path.isfile(bpy.path.abspath(props.detected_roughness_path)) else None,
            'ao': bpy.path.abspath(props.detected_ao_path) if props.detected_ao_path and os.path.isfile(bpy.path.abspath(props.detected_ao_path)) else None,
            'masks': [item.filepath for item in props.map_items if item.category == 'Mask' and item.is_assigned and os.path.isfile(item.filepath)],
        }

        # Determine subdivision levels (proportionally downscaled if tiled)
        eff_base, eff_vp, eff_ren = utils.get_effective_tile_subdivisions(props)
        is_tiled_op = (props.is_tiled and props.use_tiling) or (obj.type == 'EMPTY' and obj.get("is_tiled")) or (obj.type == 'MESH' and obj.get("is_gaea_tile"))
        sub_vp = eff_vp if is_tiled_op else props.subdiv_levels_viewport
        sub_ren = eff_ren if is_tiled_op else props.subdiv_levels_render

        success = utils.update_terrain_maps(
            obj=obj,
            detected_maps=detected_maps,
            terrain_height=props.terrain_height,
            subdiv_viewport=sub_vp,
            subdiv_render=sub_ren,
            subdiv_type=props.subdiv_type,
            use_cycles_disp=props.use_cycles_adaptive,
            mix_ao=props.mix_ambient_occlusion,
            ao_factor=props.ao_factor,
            default_roughness=props.default_roughness,
            tile_data_json=props.tile_data_json
        )

        if success:
            self.report({'INFO'}, f"Successfully updated maps on Gaea terrain '{obj.name}'.")
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, f"Failed to update maps on '{obj.name}'.")
            return {'CANCELLED'}


class GAEA_OT_frame_view(bpy.types.Operator):
    """Show the full view of the scene in the 3D Viewport (equivalent to pressing Home)"""
    bl_idname = "gaea.frame_view"
    bl_label = "Frame Scene View (Home)"
    bl_description = "Show the full view of the scene in the 3D Viewport (equivalent to pressing Home)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        success = utils.frame_scene_view()
        if success:
            self.report({'INFO'}, "Framed scene in 3D Viewport (Home).")
        else:
            self.report({'WARNING'}, "No 3D Viewport found to frame.")
        return {'FINISHED'}


class GAEA_OT_generate_uv_map(bpy.types.Operator):
    """Generate or reset top-down orthographic UV coordinates on the selected terrain mesh"""
    bl_idname = "gaea.generate_uv_map"
    bl_label = "Generate Top-Down UVs"
    bl_description = "Generate top-down planar UV coordinates matching Gaea's orthographic coordinate system"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        success = utils.ensure_mesh_uv_map(obj, force_planar=True)
        if success:
            self.report({'INFO'}, f"Generated top-down UV map on '{obj.name}'.")
        else:
            self.report({'WARNING'}, f"Could not generate UV map on '{obj.name}'.")
        return {'FINISHED'}


class GAEA_OT_pick_active_tile(bpy.types.Operator):
    """Pick coordinates from the currently selected tile in the 3D Viewport"""
    bl_idname = "gaea.pick_active_tile"
    bl_label = "Pick Active Tile"
    bl_description = "Set Tile X and Y coordinates from the currently selected tile in the viewport"

    def execute(self, context):
        props = context.scene.gaea_terrain_props
        obj = context.active_object
        if not obj or not obj.get("is_gaea_tile"):
            self.report({'WARNING'}, "Please select a Gaea tile mesh in the 3D Viewport.")
            return {'CANCELLED'}

        props.detail_tile_x = obj.get("tile_x", 0)
        props.detail_tile_y = obj.get("tile_y", 0)
        self.report({'INFO'}, f"Selected Tile set to X={props.detail_tile_x}, Y={props.detail_tile_y} ('{obj.name}')")
        return {'FINISHED'}


class GAEA_OT_auto_match_detail(bpy.types.Operator):
    """Analyze high-res heightmap and automatically solve height scale, midlevel offset, and orientation"""
    bl_idname = "gaea.auto_match_detail"
    bl_label = "Auto-Match Elevation & Flip Y"
    bl_description = "Analyze the detail folder heightmap against the base terrain and automatically calculate scale, midlevel, and orientation"

    def execute(self, context):
        props = context.scene.gaea_terrain_props
        if not props.detail_folder_path:
            self.report({'ERROR'}, "Please specify a High-Res Detail Folder first.")
            return {'CANCELLED'}

        folder_abs = bpy.path.abspath(props.detail_folder_path)
        if not folder_abs or not os.path.isdir(folder_abs):
            self.report({'ERROR'}, f"Detail folder does not exist: '{props.detail_folder_path}'")
            return {'CANCELLED'}

        tx = props.detail_tile_x
        ty = props.detail_tile_y
        detail_maps = utils.scan_detail_folder(folder_abs, target_x=tx, target_y=ty)
        if not detail_maps or not detail_maps.get('height'):
            self.report({'ERROR'}, f"No valid heightmap found in '{props.detail_folder_path}' for Tile ({tx}, {ty}).")
            return {'CANCELLED'}

        scale, mid_level, flip_y, msg = utils.auto_calibrate_detail_tile(
            context=context,
            props=props,
            tile_x=tx,
            tile_y=ty,
            detail_maps=detail_maps
        )

        props.detail_height_scale = round(scale, 3)
        props.detail_mid_level = round(mid_level, 4)
        props.detail_flip_y = flip_y
        props.detail_invert_height = False

        self.report({'INFO'}, msg)
        return {'FINISHED'}


class GAEA_OT_apply_detail_tile(bpy.types.Operator):
    """Apply high-resolution replacement maps from the detail folder to the selected tile"""
    bl_idname = "gaea.apply_detail_tile"
    bl_label = "Apply Detail Folder to Tile"
    bl_description = "Replace maps and displacement for the target tile with high-resolution maps from the detail folder"

    def execute(self, context):
        props = context.scene.gaea_terrain_props
        if not props.detail_folder_path:
            self.report({'ERROR'}, "Please specify a High-Res Detail Folder first.")
            return {'CANCELLED'}

        tx = props.detail_tile_x
        ty = props.detail_tile_y
        boost = props.detail_subdiv_boost
        keep_h = props.detail_keep_original_height

        success, msg = utils.apply_detail_to_tile(
            context=context,
            props=props,
            tile_x=tx,
            tile_y=ty,
            detail_folder_path=props.detail_folder_path,
            subdiv_boost=boost,
            height_scale=props.detail_height_scale,
            invert_height=props.detail_invert_height,
            mid_level=props.detail_mid_level,
            flip_y=props.detail_flip_y,
            auto_match=props.detail_auto_match,
            keep_height=keep_h
        )

        if success:
            self.report({'INFO'}, msg)
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, msg)
            return {'CANCELLED'}


class GAEA_OT_apply_detail_textures_only(bpy.types.Operator):
    """Apply high-resolution textures from detail folder while preserving the base height displacement seamlessly"""
    bl_idname = "gaea.apply_detail_textures_only"
    bl_label = "Replace Textures Only (Keep Base Height)"
    bl_description = "Replace surface textures (Albedo, Normal, Roughness, AO, Masks) with high-res files while keeping the original base height displacement perfectly seamless"

    def execute(self, context):
        props = context.scene.gaea_terrain_props
        if not props.detail_folder_path:
            self.report({'ERROR'}, "Please specify a High-Res Detail Folder first.")
            return {'CANCELLED'}

        props.detail_keep_original_height = True
        tx = props.detail_tile_x
        ty = props.detail_tile_y
        boost = props.detail_subdiv_boost

        success, msg = utils.apply_detail_to_tile(
            context=context,
            props=props,
            tile_x=tx,
            tile_y=ty,
            detail_folder_path=props.detail_folder_path,
            subdiv_boost=boost,
            height_scale=props.detail_height_scale,
            invert_height=False,
            mid_level=props.detail_mid_level,
            flip_y=props.detail_flip_y,
            auto_match=props.detail_auto_match,
            keep_height=True
        )

        if success:
            self.report({'INFO'}, msg)
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, msg)
            return {'CANCELLED'}


classes = (
    GAEA_OT_scan_folder,
    GAEA_OT_clear_slots,
    GAEA_OT_import_terrain,
    GAEA_OT_setup_material,
    GAEA_OT_update_terrain_maps,
    GAEA_OT_frame_view,
    GAEA_OT_generate_uv_map,
    GAEA_OT_pick_active_tile,
    GAEA_OT_auto_match_detail,
    GAEA_OT_apply_detail_tile,
    GAEA_OT_apply_detail_textures_only,
)



def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
