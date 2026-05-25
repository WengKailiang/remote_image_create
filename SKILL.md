---
name: arcgis-remote-sensing-image-merging
description: Use when processing Landsat 8 OLI_TIRS remote-sensing image archives with ArcGIS Desktop/ArcPy, especially workflows that first create a `原始数据提供` intake folder, import Landsat true-color `B4/B3/B2`, study-area shapefiles, optional landslide and hydropower point data into a `遥感图像处理结果` package, reproject/mosaic/clip imagery, generate Chinese-named ArcMap layers, and export a publication-style layout map while keeping outputs and temporary files off the C drive.
---

# ArcGIS Remote Sensing Image Merging

## Overview

Process Landsat 8 OLI_TIRS scenes into ArcGIS-ready true-color results: first create a clear `原始数据提供` intake folder, let the user place raw files there, then import those files into `遥感图像处理结果\原始数据`, extract `B4/B3/B2`, match the study-area shapefile coordinate system, build a full-scene RGB image, clip the study-area image, create one MXD containing both raster results, export a publication-style layout map, and keep reusable outputs separate from files that can be deleted.

Prefer Landsat 8 OLI_TIRS data packages that contain actual band files such as `*_B2.TIF`, `*_B3.TIF`, and `*_B4.TIF`. A package containing only QA or metadata files is not enough for true-color imagery.

## Required Inputs

Before calculation, create the project folder structure for the user instead of asking them to invent paths. The user should first put raw files in `原始数据提供`; the script imports them into the processing package when calculation starts.

Required folders and inputs:

- A workspace-level intake folder named `原始数据提供`.
- A `原始数据提供\所需原始数据说明.txt` file explaining what the user should place in the intake folder.
- A `原始数据提供\landsat8_source` folder containing Landsat 8 OLI_TIRS `.tar`, `.tar.gz`, `.tgz`, or extracted `.tif` bands.
- A `原始数据提供\study_area_boundary` folder containing the study-area shapefile.
- Optional: a `原始数据提供\滑坡点与水电站位置` folder containing `landslide_points.shp` with sidecars and the generated `倾泻点.csv` hydropower template filled with `Longitude` and `Latitude`.
- A final output package folder named `遥感图像处理结果`.
- A `遥感图像处理结果\原始数据` folder where the script stores imported Landsat, boundary, point, and explanatory text files.
- The archive must contain true-color bands: `B4` red, `B3` green, and `B2` blue. If only `QA_PIXEL`, `BQA`, `MTL`, or `ANG` files are present, stop and ask the user to download the full Landsat 8 OLI_TIRS product with all bands.
- A complete study-area shapefile set: `.shp`, `.shx`, `.dbf`, `.prj`, and sidecar files.
- A project/output folder on a non-C drive, usually `遥感图像处理结果\landsat8_work`. Keep `00_original_data`, `01_intermediate`, `02_outputs`, `03_arcmap`, and `_scratch` under this folder during processing.
- ArcGIS Desktop 10.x / ArcPy, usually `C:\Python27\ArcGIS10.8\python.exe`.
- An ArcMap template MXD path, usually under the ArcGIS installation directory.

If the shapefile lacks `.prj`, stop and ask the user for the correct coordinate system.

## Workflow

1. Initialize the workspace first. This creates the user-facing intake folder plus the final processing package:
   - `原始数据提供`
   - `原始数据提供\landsat8_source`
   - `原始数据提供\study_area_boundary`
   - `原始数据提供\滑坡点与水电站位置`
   - `原始数据提供\所需原始数据说明.txt`
   - `原始数据提供\滑坡点与水电站位置\倾泻点.csv`
   - `遥感图像处理结果\原始数据`
   - `遥感图像处理结果\landsat8_work`
   - `遥感图像处理结果\可以删除`
   - `遥感图像处理结果\config.landsat8.local.json`
2. Inside `landsat8_work`, create processing folders:
   - `00_original_data`
   - `01_intermediate`
   - `02_outputs`
   - `03_arcmap`
   - `04_layout_map`
   - `_scratch`
3. Stop after initialization and ask the user to place:
   - Landsat 8 OLI_TIRS `.tar`, `.tar.gz`, `.tgz`, or extracted band `.TIF` files into `原始数据提供\landsat8_source`.
   - Complete study-area shapefile components into `原始数据提供\study_area_boundary`.
   - Optional `landslide_points.*` into `原始数据提供\滑坡点与水电站位置`, and fill the generated `倾泻点.csv` template for hydropower points.
4. After the user confirms files are in place, run calculation with the generated config. The script copies raw data and explanatory text from `原始数据提供` into `遥感图像处理结果\原始数据`.
5. Set `TEMP`, `TMP`, `ARCTMPDIR`, `arcpy.env.workspace`, and `arcpy.env.scratchWorkspace` to project-local folders before heavy ArcPy work.
6. Copy the study-area shapefile components into `00_original_data/study_area_boundary`.
7. For large remote-sensing archives, avoid unnecessary full duplication unless the user explicitly requests it. Extract only the configured bands into `00_original_data/remote_sensing/extracted_scenes`.
8. Use the study-area shapefile spatial reference as the target coordinate system.
9. Reproject every selected raster band to the target coordinate system with bilinear resampling for continuous imagery.
10. Convert fill values such as `0` to NoData before mosaicking.
11. Mosaic each band across all scenes.
12. Composite bands in display order. Default true-color Landsat 8 order is `B4`, `B3`, `B2`.
13. Clip the complete mosaic by the study-area shapefile.
14. Create one MXD containing Chinese-named layers:
    - `研究区边界`
    - `研究区遥感影像（裁剪结果）`
    - `完整遥感影像（拼接结果）`
15. Export a publication-style layout map PNG in `landsat8_work\04_layout_map`, including latitude/longitude frame labels derived from the actual project extent, north arrow, scale bar, legend, study-area boundary, optional landslide red triangles, and optional hydropower red star.
16. Save file outputs with English names to reduce ArcGIS path/name issues, but use Chinese layer names inside ArcMap.
17. Keep final rasters, the comprehensive MXD, and layout PNG in `landsat8_work\02_outputs`, `03_arcmap`, and `04_layout_map`.
18. Move re-creatable processing folders such as `原始数据提供`, `00_original_data`, `01_intermediate`, `_scratch`, and helper logs/scripts into `遥感图像处理结果\可以删除`. Do not move the full mosaic, clipped raster, imported source archive, study-area shapefile, point inputs, comprehensive MXD, or layout PNG there.

## Scripted Execution

Use `scripts/process_remote_sensing_arcgis108.py` with ArcGIS Python:

Initialize the workspace first. Pass the working folder, not the final package folder:

```powershell
& 'C:\Python27\ArcGIS10.8\python.exe' 'path\to\arcgis-remote-sensing-image-merging\scripts\process_remote_sensing_arcgis108.py' --init-project 'F:\path\to\project' --output-prefix 'liangcheng_landsat8'
```

After the user places data into `原始数据提供`, run:

```powershell
$env:TEMP='F:\path\to\project\_scratch'
$env:TMP='F:\path\to\project\_scratch'
$env:ARCTMPDIR='F:\path\to\project\_scratch'
& 'C:\Python27\ArcGIS10.8\python.exe' 'path\to\arcgis-remote-sensing-image-merging\scripts\process_remote_sensing_arcgis108.py' --config 'F:\path\to\project\遥感图像处理结果\config.landsat8.local.json'
```

The `--init-project` mode writes `config.landsat8.local.json` automatically. If creating the config manually, start from `references/config-template.json` and update `project_root`, `remote_sensing_source_dir`, `study_area_shp`, `delete_folder`, and `arcmap_template_mxd` before running.

Use this tested folder pattern:

```text
remote_sensing_source_dir = ...\遥感图像处理结果\原始数据\landsat8_source
study_area_shp = ...\遥感图像处理结果\原始数据\study_area_boundary\study_area_boundary.shp
points_source_dir = ...\遥感图像处理结果\原始数据\滑坡点与水电站位置
hydropower_csv = ...\遥感图像处理结果\原始数据\滑坡点与水电站位置\倾泻点.csv
project_root = ...\遥感图像处理结果\landsat8_work
delete_folder = ...\遥感图像处理结果\可以删除
band_tokens = ["B4", "B3", "B2"]
raw_intake_dir = ...\原始数据提供
import_raw_data_from_intake = true
create_layout_map = true
```

Change `band_tokens` to `["B5", "B4", "B3"]` for false-color vegetation display.

## Validation

After processing, check:

- `02_outputs/*_full_mosaic.tif` exists and uses the study-area shapefile coordinate system.
- `02_outputs/*_study_area_clip.tif` exists and is clipped to the study-area boundary.
- `03_arcmap/*_arcmap.mxd` opens in ArcMap data view.
- `04_layout_map/*_layout_map.png` exists. Its longitude/latitude frame labels must be generated from the current raster/study-area coordinate system, not copied from a reference figure.
- If hydropower points are needed, `原始数据提供\滑坡点与水电站位置\倾泻点.csv` should be the user-filled template with fields `ID,NAME,Longitude,Latitude`; if it only has the header, the layout map should skip hydropower points without failing.
- ArcMap layer names are Chinese, even though output file names are English.
- All outputs, scratch files, extracted bands, `.lyr`, `.mxd`, pyramids, statistics, and sidecars are inside the project folder, not on `C:\`.
- If the clipped image looks more saturated than the full image, check display statistics before assuming a data problem. ArcMap often stretches each raster independently; clipped rasters usually have narrower min/max ranges and therefore appear higher contrast. Layer transparency should remain `0` unless the user explicitly asks for transparency.
- `遥感图像处理结果\landsat8_work\02_outputs` keeps both `*_full_mosaic.tif` and `*_study_area_clip.tif`.
- `遥感图像处理结果\landsat8_work\03_arcmap` keeps one comprehensive `*_arcmap.mxd` plus the `.lyr` files it needs.
- `遥感图像处理结果\landsat8_work\04_layout_map` keeps the layout map PNG.
- `遥感图像处理结果\可以删除` contains only re-creatable intermediate files and temporary helper artifacts.
- `原始数据提供` is moved into `遥感图像处理结果\可以删除` after successful processing, because its contents have been copied into `遥感图像处理结果\原始数据`.

## Safety

Never use recursive delete commands. If old intermediate folders or obsolete rasters need cleanup, list them for the user to delete manually, or delete only one explicit file path at a time.
