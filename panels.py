"""
UI Panels for CEB_Gaea2Blender add-on.
Displays the Gaea import interface in the 3D Viewport Sidebar ('Gaea' tab).
"""

import os
import bpy
from . import utils


class GAEA_PT_main_panel(bpy.types.Panel):
    """Main Sidebar Panel for Gaea terrain importing"""
    bl_label = "Gaea 2 Blender Importer"
    bl_idname = "GAEA_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "CEB"

    def draw(self, context):
        layout = self.layout
        props = context.scene.gaea_terrain_props
        active_obj = context.active_object
        is_terrain = bool(active_obj and utils.is_gaea_terrain(active_obj))

        # --- ACTIVE TERRAIN DETECTED BANNER ---
        if is_terrain:
            box_active = layout.box()
            t_type = active_obj.get("gaea_type", "Terrain")
            box_active.label(text=f"Selected: {active_obj.name} ({t_type})", icon='CHECKMARK')
            if active_obj.get("is_gaea_tile"):
                row_tile_info = box_active.row(align=True)
                row_tile_info.label(text=f"Tile Coord: ({active_obj.get('tile_x')}, {active_obj.get('tile_y')})", icon='GRID')
                row_tile_info.operator("gaea.pick_active_tile", text="Set as Detail Target", icon='RESTRICT_SELECT_OFF')
            row_up = box_active.row(align=True)
            row_up.scale_y = 1.4
            row_up.operator("gaea.update_terrain_maps", text="Update Selected Terrain with Maps", icon='FILE_REFRESH')

        # --- SECTION 1: Folder Selection & Scanner ---
        box_scan = layout.box()
        box_scan.label(text="Gaea Export Folder", icon='FILE_FOLDER')
        box_scan.prop(props, "folder_path", text="")

        row_scan = box_scan.row(align=True)
        row_scan.operator("gaea.scan_folder", text="Scan Output Folder", icon='VIEWZOOM')
        row_scan.operator("gaea.clear_slots", text="", icon='X')

        # Status badge
        if props.has_scanned:
            box_stat = box_scan.box()
            row_stat = box_stat.row()
            row_stat.label(text=props.scan_status, icon='CHECKMARK')
        elif props.folder_path:
            box_scan.label(text="Click 'Scan Output Folder' to analyze", icon='INFO')

        # Check available sources
        mesh_file = bpy.path.abspath(props.detected_mesh_path) if props.detected_mesh_path else ""
        height_file = bpy.path.abspath(props.detected_height_path) if props.detected_height_path else ""
        has_mesh = bool(mesh_file and os.path.isfile(mesh_file))
        has_height = bool(height_file and os.path.isfile(height_file))

        is_mesh = (props.import_mode == 'MESH')
        if not is_mesh and not has_height and has_mesh:
            is_mesh = True

        # --- TILED TERRAIN DETECTED BOX ---
        if props.has_scanned and props.is_tiled:
            box_tile = layout.box()
            row_tile_hdr = box_tile.row(align=True)
            row_tile_hdr.label(text=f"Tiled Terrain: {props.tile_grid_info} ({props.tile_total_count} tiles)", icon='GRID')
            box_tile.prop(props, "use_tiling", text="Load as Tiled Terrain")

            if props.use_tiling:
                col_tinfo = box_tile.column(align=True)
                tile_w = props.terrain_width / max(1, props.tile_cols)
                tile_l = props.terrain_length / max(1, props.tile_rows)
                col_tinfo.label(text=f"Per Tile: {tile_w:.1f} m x {tile_l:.1f} m  (Total: {props.terrain_width:.1f} m x {props.terrain_length:.1f} m)", icon='INFO')
                col_tinfo.prop(props, "tile_flip_y", text="Flip Y Row Order (Y0 at North)")

                # Detail / High-Res Tile Replacement Section
                box_dt = box_tile.box()
                row_dt_toggle = box_dt.row(align=True)
                icon_dt = 'DISCLOSURE_TRI_DOWN' if props.show_detail_tile_settings else 'DISCLOSURE_TRI_RIGHT'
                row_dt_toggle.prop(props, "show_detail_tile_settings", text="Detail / High-Res Tile Override", icon=icon_dt, emboss=False)

                if props.show_detail_tile_settings:
                    col_dt = box_dt.column(align=True)
                    col_dt.prop(props, "enable_tile_override", text="Replace Tile with High-Res Folder")

                    if props.enable_tile_override or props.detail_folder_path:
                        col_dt.label(text="High-Res Folder (e.g. 2k/4k maps):", icon='FILE_FOLDER')
                        col_dt.prop(props, "detail_folder_path", text="")

                        row_tcoords = col_dt.row(align=True)
                        row_tcoords.prop(props, "detail_tile_x", text="Tile X")
                        row_tcoords.prop(props, "detail_tile_y", text="Tile Y")
                        row_tcoords.operator("gaea.pick_active_tile", text="", icon='RESTRICT_SELECT_OFF')

                        row_sub_boost = col_dt.row(align=True)
                        row_sub_boost.prop(props, "detail_subdiv_boost", text="Extra Subdiv Levels")

                        row_keep = col_dt.row(align=True)
                        row_keep.prop(props, "detail_keep_original_height", text="Keep Original Height (Seamless Mesh)")

                        row_auto = col_dt.row(align=True)
                        row_auto.prop(props, "detail_auto_match", text="Auto-Match Elevation & Flip Y")
                        row_auto.operator("gaea.auto_match_detail", text="Auto-Detect", icon='AUTO')

                        if not props.detail_keep_original_height:
                            row_scale = col_dt.row(align=True)
                            row_scale.prop(props, "detail_height_scale", text="Height Scale")
                            row_scale.prop(props, "detail_mid_level", text="Midlevel")

                            row_toggles = col_dt.row(align=True)
                            row_toggles.prop(props, "detail_invert_height", text="Invert Height", toggle=True)
                            row_toggles.prop(props, "detail_flip_y", text="Flip Y", toggle=True)
                        else:
                            row_toggles = col_dt.row(align=True)
                            row_toggles.prop(props, "detail_flip_y", text="Flip Textures Y", toggle=True)

                        # Primary action button: Textures only (Keep base height seamless)
                        row_btn1 = col_dt.row(align=True)
                        row_btn1.scale_y = 1.3
                        row_btn1.operator(
                            "gaea.apply_detail_textures_only",
                            text="Replace Textures Only (Keep Base Height)",
                            icon='MATERIAL'
                        )

                        # Secondary action button: Full replacement including height displacement
                        row_btn2 = col_dt.row(align=True)
                        row_btn2.scale_y = 1.1
                        row_btn2.operator(
                            "gaea.apply_detail_tile",
                            text="Replace All Maps (Inc. Height Displacement)",
                            icon='FILE_REFRESH'
                        )

        # --- SELECTION BUTTONS (When both Height Map and Mesh are detected) ---
        if has_height and has_mesh and not (props.is_tiled and props.use_tiling):
            box_choice = layout.box()
            row_choice_title = box_choice.row(align=True)
            row_choice_title.label(text="Select Terrain Source to Load:", icon='IMPORT')
            row_choice_btns = box_choice.row(align=True)
            row_choice_btns.scale_y = 1.3
            row_choice_btns.prop_enum(props, "import_mode", 'HEIGHTMAP', text="Height Map", icon='IMAGE_DATA')
            row_choice_btns.prop_enum(props, "import_mode", 'MESH', text="3D Mesh", icon='MESH_DATA')

        # --- SECTION 2: Geometry & Subdivisions ---
        box_geo = layout.box()
        row_geo_toggle = box_geo.row(align=True)
        icon_geo = 'DISCLOSURE_TRI_DOWN' if props.show_geometry_settings else 'DISCLOSURE_TRI_RIGHT'
        row_geo_toggle.prop(props, "show_geometry_settings", text="Geometry & Subdivisions", icon=icon_geo, emboss=False)

        if props.show_geometry_settings:
            col_geo = box_geo.column()
            col_geo.prop(props, "import_mode", text="Mode")

            if is_mesh:
                box_geo.label(text="Subdivisions apply only to Height Map plane mode.", icon='INFO')
            else:
                col_sub = col_geo.column(align=True)
                col_sub.prop(props, "base_subdivisions")
                col_sub.prop(props, "subdiv_levels_viewport")
                col_sub.prop(props, "subdiv_levels_render")
                col_geo.prop(props, "subdiv_type", text="Subdiv Type")
                col_geo.prop(props, "use_cycles_adaptive")

                if props.is_tiled and props.use_tiling:
                    box_tscale = col_geo.box()
                    box_tscale.prop(props, "auto_scale_tiled_subdiv", text="Scale Subdivisions for Tiles")
                    if props.auto_scale_tiled_subdiv:
                        eff_base, eff_vp, eff_ren = utils.get_effective_tile_subdivisions(props)
                        col_tstat = box_tscale.column(align=True)
                        col_tstat.label(
                            text=f"Effective per tile ({props.tile_grid_info}):",
                            icon='INFO'
                        )
                        col_tstat.label(
                            text=f"Base: {eff_base} | Viewport: {eff_vp} | Render: {eff_ren}",
                            icon='BLANK1'
                        )

        # --- SECTION 3: Terrain Dimensions ---
        box_dim = layout.box()
        row_dim_toggle = box_dim.row(align=True)
        icon_dim = 'DISCLOSURE_TRI_DOWN' if props.show_dimension_settings else 'DISCLOSURE_TRI_RIGHT'
        dim_title = "Terrain Dimensions (Ignored for Mesh)" if is_mesh else "Terrain Dimensions"
        row_dim_toggle.prop(props, "show_dimension_settings", text=dim_title, icon=icon_dim, emboss=False)

        if props.show_dimension_settings:
            if is_mesh:
                box_notice = box_dim.box()
                box_notice.label(text="Mesh Selected: Terrain dimensions are ignored.", icon='INFO')
                box_notice.label(text="Native mesh scale & geometry will be preserved.", icon='BLANK1')

            col_dim = box_dim.column(align=True)
            col_dim.enabled = not is_mesh
            col_dim.prop(props, "terrain_width", text="Width (X)")
            col_dim.prop(props, "terrain_length", text="Length (Y)")
            col_dim.prop(props, "terrain_height", text="Elevation (Z)")

            row_orig = box_dim.row()
            row_orig.enabled = not is_mesh
            row_orig.prop(props, "terrain_origin", expand=True)

        # --- SECTION 4: Map Correspondences ---
        box_corr = layout.box()
        used_files = utils.get_used_filenames(props)
        mapped_items = [i for i in props.map_items if i.is_assigned and i.category != 'Unused']
        unmapped_items = [i for i in props.map_items if not i.is_assigned and i.category != 'Unused']
        unused_items = [i for i in props.map_items if i.category == 'Unused' and not i.is_assigned and i.filename not in used_files]
        count_str = f"({len(mapped_items)} mapped)" if props.has_scanned else ""

        row_corr_toggle = box_corr.row(align=True)
        icon_corr = 'DISCLOSURE_TRI_DOWN' if props.show_map_correspondences else 'DISCLOSURE_TRI_RIGHT'
        row_corr_toggle.prop(props, "show_map_correspondences", text=f"Detected Maps Correspondence {count_str}", icon=icon_corr, emboss=False)

        if props.show_map_correspondences:
            if props.has_scanned and len(props.map_items) > 0:
                # Successfully identified maps (aligned column for compact rows like missing slots)
                if mapped_items:
                    col_mapped = box_corr.column(align=True)
                    for item in mapped_items:
                        box_item = col_mapped.box()
                        col_item = box_item.column(align=True)

                        row_top = col_item.row(align=True)
                        row_top.label(text=item.slot_name, icon=item.icon_name)
                        if props.is_tiled and props.use_tiling:
                            row_top.label(text=item.filename, icon='IMAGE_DATA')
                        else:
                            row_top.prop(item, "selected_file", text="")

                        if item.category == 'Roughness' and (not item.is_assigned or item.selected_file == 'NONE'):
                            row_rough = col_item.row(align=True)
                            row_rough.prop(props, "default_roughness", slider=True, text="Roughness Value")

                # Unmapped / missing standard slots (with dropdown to pick from folder)
                if unmapped_items and not (props.is_tiled and props.use_tiling):
                    col_missing = box_corr.column(align=True)
                    col_missing.separator()
                    col_missing.label(text="Missing Slots (Select image from folder):", icon='ERROR')
                    for item in unmapped_items:
                        box_un = col_missing.box()
                        col_un = box_un.column(align=True)

                        row_un = col_un.row(align=True)
                        row_un.label(text=f"{item.slot_name}:", icon=item.icon_name)
                        row_un.prop(item, "selected_file", text="")

                        if item.category == 'Roughness':
                            row_rough = col_un.row(align=True)
                            row_rough.prop(props, "default_roughness", slider=True, text="Roughness Value")

                # Other files in folder (not matching any map, shown as unused)
                if unused_items and not (props.is_tiled and props.use_tiling):
                    col_unused = box_corr.column(align=True)
                    col_unused.separator()
                    col_unused.label(text=f"Other Files in Folder ({len(unused_items)} unused):", icon='FILE')
                    box_u = col_unused.box()
                    col_u = box_u.column(align=True)
                    max_display = 6
                    for item in unused_items[:max_display]:
                        row_u = col_u.row(align=True)
                        row_u.label(text=item.filename, icon='IMAGE_DATA')
                    if len(unused_items) > max_display:
                        row_more = col_u.row(align=True)
                        row_more.label(text=f"... and {len(unused_items) - max_display} more file(s)", icon='THREE_DOTS')

            elif props.folder_path:
                box_corr.label(text="Click 'Scan Output Folder' to identify and map files.", icon='INFO')
            else:
                box_corr.label(text="Select a folder to view map correspondences.", icon='INFO')

        # --- SECTION 5: Material & Shading ---
        box_mat = layout.box()
        row_mat_toggle = box_mat.row(align=True)
        icon_mat = 'DISCLOSURE_TRI_DOWN' if props.show_material_settings else 'DISCLOSURE_TRI_RIGHT'
        row_mat_toggle.prop(props, "show_material_settings", text="Material & Shading", icon=icon_mat, emboss=False)

        if props.show_material_settings:
            col_mat = box_mat.column()
            col_mat.prop(props, "smooth_shading")

            row_ao = col_mat.row()
            row_ao.prop(props, "mix_ambient_occlusion")
            if props.mix_ambient_occlusion:
                col_mat.prop(props, "ao_factor", slider=True)

            if not props.detected_roughness_path:
                col_mat.prop(props, "default_roughness", slider=True, text="Roughness Value")

            # UV & Material Actions on active object
            if active_obj and active_obj.type == 'MESH':
                row_uv = col_mat.row(align=True)
                row_uv.operator("gaea.generate_uv_map", text="Generate Top-Down UVs", icon='UV')

            # Update material / maps on active object
            if is_terrain:
                col_mat.operator("gaea.update_terrain_maps", text="Update Selected Terrain with Maps", icon='SHADING_TEXTURE')
            elif active_obj and active_obj.type == 'MESH':
                col_mat.operator("gaea.setup_material", text="Rebuild Material on Active", icon='SHADING_TEXTURE')

        # --- SECTION 6: Detected Files & Overrides ---
        box_files = layout.box()
        row_toggle = box_files.row()
        icon_expand = 'DISCLOSURE_TRI_DOWN' if props.show_file_slots else 'DISCLOSURE_TRI_RIGHT'
        row_toggle.prop(props, "show_file_slots", text="Detected File Overrides", icon=icon_expand, emboss=False)

        if props.show_file_slots:
            col_slots = box_files.column(align=True)

            def draw_slot(label, prop_name, file_path):
                row = col_slots.row(align=True)
                has_file = bool(file_path and os.path.exists(file_path))
                status_icon = 'CHECKMARK' if has_file else 'BLANK1'
                row.label(text=label, icon=status_icon)
                row.prop(props, prop_name, text="")

            draw_slot("Mesh:", "detected_mesh_path", props.detected_mesh_path)
            draw_slot("Height:", "detected_height_path", props.detected_height_path)
            draw_slot("Normal:", "detected_normal_path", props.detected_normal_path)
            draw_slot("Albedo:", "detected_albedo_path", props.detected_albedo_path)
            draw_slot("Rough:", "detected_roughness_path", props.detected_roughness_path)
            draw_slot("AO:", "detected_ao_path", props.detected_ao_path)

        # --- SECTION 7: Action Buttons ---
        layout.separator()
        if is_terrain:
            row_update = layout.row()
            row_update.scale_y = 1.6
            row_update.operator("gaea.update_terrain_maps", text=f"Update Maps on '{active_obj.name}'", icon='FILE_REFRESH')

        row_view = layout.row(align=True)
        row_view.prop(props, "auto_frame_view", text="Auto Full View on Load (Home)", icon='ZOOM_ALL')
        row_view.operator("gaea.frame_view", text="", icon='HOME')

        row_action = layout.row()
        row_action.scale_y = 1.4 if is_terrain else 1.8
        if props.is_tiled and props.use_tiling:
            mode_suffix = f" (Tiled: {props.tile_grid_info})"
        else:
            mode_suffix = " (Mesh)" if is_mesh else " (Height Map)"
        btn_text = f"Create New Terrain{mode_suffix}" if is_terrain else f"Import & Build Terrain{mode_suffix}"
        row_action.operator("gaea.import_terrain", text=btn_text, icon='IMPORT')


classes = (
    GAEA_PT_main_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
