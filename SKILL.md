---
name: remote-sensing-image-merging
description: Use when processing Landsat 8 OLI_TIRS remote-sensing image archives with ArcGIS Desktop/ArcPy, especially `.tar` or `.tar.gz` packages containing true-color bands `B4/B3/B2` that must be organized, reprojected to a study-area shapefile coordinate system, composited into a complete image, clipped by the study area, and displayed in ArcMap with Chinese layer names while keeping all outputs and temporary files off the C drive.
---

# Remote Sensing Image Merging

## Overview

Process Landsat 8 OLI_TIRS scenes into ArcGIS-ready true-color results: organize inputs, extract `B4/B3/B2`, match the study-area shapefile coordinate system, build a full-scene RGB image, clip the study-area image, create one MXD containing both results, and keep reusable outputs separate from files that can be deleted.

Prefer Landsat 8 OLI_TIRS data packages that contain actual band files such as `*_B2.TIF`, `*_B3.TIF`, and `*_B4.TIF`. A package containing only QA or metadata files is not enough for true-color imagery.

## Required Inputs

Before running the workflow, confirm:

- A final output package folder named `遥感图像处理结果`.
- A `遥感图像处理结果\原始数据\landsat8_source` folder containing Landsat 8 OLI_TIRS `.tar` or `.tar.gz` archives, or extracted `.tif` bands.
- A `遥感图像处理结果\原始数据\study_area_boundary` folder containing the study-area shapefile.
- The archive must contain true-color bands: `B4` red, `B3` green, and `B2` blue. If only `QA_PIXEL`, `BQA`, `MTL`, or `ANG` files are present, stop and ask the user to download the full Landsat 8 OLI_TIRS product with all bands.
- A complete study-area shapefile set: `.shp`, `.shx`, `.dbf`, `.prj`, and sidecar files.
- A project/output folder on a non-C drive, usually `遥感图像处理结果\landsat8_work`. Keep `00_original_data`, `01_intermediate`, `02_outputs`, `03_arcmap`, and `_scratch` under this folder during processing.
- ArcGIS Desktop 10.x / ArcPy, usually `C:\Python27\ArcGIS10.8\python.exe`.
- An ArcMap template MXD path, usually under the ArcGIS installation directory.

If the shapefile lacks `.prj`, stop and ask the user for the correct coordinate system.

## Workflow

1. Create this final package structure:
   - `遥感图像处理结果\原始数据\landsat8_source`
   - `遥感图像处理结果\原始数据\study_area_boundary`
   - `遥感图像处理结果\landsat8_work`
   - `遥感图像处理结果\可以删除`
2. Inside `landsat8_work`, create processing folders:
   - `00_original_data`
   - `01_intermediate`
   - `02_outputs`
   - `03_arcmap`
   - `_scratch`
3. Set `TEMP`, `TMP`, `ARCTMPDIR`, `arcpy.env.workspace`, and `arcpy.env.scratchWorkspace` to project-local folders before heavy ArcPy work.
4. Copy the study-area shapefile components into `00_original_data/study_area_boundary`.
5. For large remote-sensing archives, avoid unnecessary full duplication unless the user explicitly requests it. Extract only the configured bands into `00_original_data/remote_sensing/extracted_scenes`.
6. Use the study-area shapefile spatial reference as the target coordinate system.
7. Reproject every selected raster band to the target coordinate system with bilinear resampling for continuous imagery.
8. Convert fill values such as `0` to NoData before mosaicking.
9. Mosaic each band across all scenes.
10. Composite bands in display order. Default true-color Landsat 8 order is `B4`, `B3`, `B2`.
11. Clip the complete mosaic by the study-area shapefile.
12. Create one MXD containing Chinese-named layers:
    - `研究区边界`
    - `研究区遥感影像（裁剪结果）`
    - `完整遥感影像（拼接结果）`
13. Save file outputs with English names to reduce ArcGIS path/name issues, but use Chinese layer names inside ArcMap.
14. Keep final rasters and the comprehensive MXD in `landsat8_work\02_outputs` and `landsat8_work\03_arcmap`.
15. Move re-creatable processing folders such as `00_original_data`, `01_intermediate`, and `_scratch` into `遥感图像处理结果\可以删除`. Do not move the full mosaic, clipped raster, source archive, study-area shapefile, or comprehensive MXD there.

## Scripted Execution

Use `scripts/process_remote_sensing_arcgis108.py` with ArcGIS Python:

```powershell
$env:TEMP='F:\path\to\project\_scratch'
$env:TMP='F:\path\to\project\_scratch'
$env:ARCTMPDIR='F:\path\to\project\_scratch'
& 'C:\Python27\ArcGIS10.8\python.exe' 'path\to\remote-sensing-image-merging\scripts\process_remote_sensing_arcgis108.py' --config 'path\to\config.json'
```

Create the config from `references/config-template.json`. Update `project_root`, `remote_sensing_source_dir`, `study_area_shp`, and `arcmap_template_mxd` before running.

Use this tested folder pattern:

```text
remote_sensing_source_dir = ...\遥感图像处理结果\原始数据\landsat8_source
study_area_shp = ...\遥感图像处理结果\原始数据\study_area_boundary\study_area_boundary.shp
project_root = ...\遥感图像处理结果\landsat8_work
delete_folder = ...\遥感图像处理结果\可以删除
band_tokens = ["B4", "B3", "B2"]
```

Change `band_tokens` to `["B5", "B4", "B3"]` for false-color vegetation display.

## Validation

After processing, check:

- `02_outputs/*_full_mosaic.tif` exists and uses the study-area shapefile coordinate system.
- `02_outputs/*_study_area_clip.tif` exists and is clipped to the study-area boundary.
- `03_arcmap/*_arcmap.mxd` opens in ArcMap data view.
- ArcMap layer names are Chinese, even though output file names are English.
- All outputs, scratch files, extracted bands, `.lyr`, `.mxd`, pyramids, statistics, and sidecars are inside the project folder, not on `C:\`.
- If the clipped image looks more saturated than the full image, check display statistics before assuming a data problem. ArcMap often stretches each raster independently; clipped rasters usually have narrower min/max ranges and therefore appear higher contrast. Layer transparency should remain `0` unless the user explicitly asks for transparency.
- `遥感图像处理结果\landsat8_work\02_outputs` keeps both `*_full_mosaic.tif` and `*_study_area_clip.tif`.
- `遥感图像处理结果\landsat8_work\03_arcmap` keeps one comprehensive `*_arcmap.mxd` plus the `.lyr` files it needs.
- `遥感图像处理结果\可以删除` contains only re-creatable intermediate files and temporary helper artifacts.

## Safety

Never use recursive delete commands. If old intermediate folders or obsolete rasters need cleanup, list them for the user to delete manually, or delete only one explicit file path at a time.
