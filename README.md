# CEB Gaea to Blender Importer

A Blender add-on that imports generated terrain assets from **QuadSpinner Gaea** directly into Blender.

## Features

- **Automatic File Scanning & Classification**:
  - Automatically identifies Meshes (`.obj`, `.fbx`, `.ply`), Heightmaps (`.exr`, `.png`, `.tif`), Normal maps, Albedo / Color maps, Roughness, Ambient Occlusion, and auxiliary masks.
  - Manual override slots to inspect and adjust any detected map before importing.
- **Custom Terrain Dimensions**:
  - Set real-world Width ($X$), Length ($Y$), and maximum Elevation ($Z$) in meters.
  - Configurable origin alignment: **Center** or **Bottom-Left Corner**.
- **High-Resolution Heightmap Subdivisions**:
  - Generates an optimized quad grid plane with configurable base subdivisions.
  - Configurable Subdivision Surface modifier levels for real-time viewport and high-detail rendering.
  - Displace modifier configured with precise real-world terrain elevation scaling and zero-based Gaea midlevel.
  - Optional Cycles micro-displacement (adaptive true displacement).
- **Imported Mesh Scaling**:
  - Imports pre-meshed terrains exported from Gaea (`.obj`, `.fbx`, `.ply`) and scales them to match the target terrain bounding dimensions ($X, Y, Z$).
- **Automated PBR Material Network**:
  - Automatically sets up a Principled BSDF shader network with appropriate color spaces (`sRGB` for albedo, `Non-Color` for normal, roughness, height, and masks).
  - Optional Ambient Occlusion blending directly into Base Color.
  - Places auxiliary masks in the shader graph for easy texturing and blending.
- **Automatic Scene Framing (Home View)**:
  - Automatically frames the entire scene in the 3D Viewport upon terrain loading (equivalent to pressing the `Home` key), ensuring large-scale landscapes are immediately and completely visible.
  - Adapts viewport clipping distance (`clip_end`) so large terrains are never clipped.
  - Includes a toggle to enable/disable auto-framing, plus a dedicated manual **Frame Scene View (Home)** button in the sidebar.

---

## Installation

1. Compress the `CEB_Gaea2Blender` folder into a `.zip` archive (or place the folder in your Blender user scripts `addons` directory: `%APPDATA%\Blender Foundation\Blender\<version>\scripts\addons\CEB_Gaea2Blender`).
2. In Blender, navigate to **Edit > Preferences > Add-ons**.
3. Click **Install...** (or search for `CEB Gaea to Blender Importer`) and enable the checkmark.

---

## How to Use

1. Open the 3D Viewport and press `N` to open the sidebar.
2. Click on the **Gaea** tab.
3. In **Gaea Export Folder**, select the directory containing your exported Gaea files.
4. Click **Scan Output Folder**. The add-on will inspect the folder and report the detected meshes and texture maps.
5. Set your desired **Terrain Dimensions**:
   - **Width (X)**: e.g. `2048 m`
   - **Length (Y)**: e.g. `2048 m`
   - **Elevation (Z)**: e.g. `500 m`
6. Select your **Import Mode**:
   - `Auto Detect`: Imports a mesh if found, otherwise generates a displaced plane.
   - `Heightmap Plane`: Generates a subdivision grid displaced by the heightmap.
   - `Imported Mesh`: Imports the 3D mesh and fits it to the terrain dimensions.
7. If using Heightmap mode, customize the **Subdivision** settings:
   - **Base Subdivisions**: Base quad grid resolution (e.g. 64).
   - **Viewport Subdiv**: Real-time viewport preview level (e.g. 3 or 4).
   - **Render Subdiv**: High-resolution render level (e.g. 6).
8. Click **Import & Build Terrain**.
