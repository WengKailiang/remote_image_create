# -*- coding: utf-8 -*-
from __future__ import print_function

import argparse
import codecs
import datetime
import json
import os
import shutil
import sys
import tarfile
import traceback


PY2 = sys.version_info[0] == 2
try:
    unicode
except NameError:
    unicode = str


def load_json(path):
    with codecs.open(path, "r", "utf-8") as handle:
        return json.load(handle)


def ensure_dir(path):
    if not os.path.isdir(path):
        os.makedirs(path)


def utext(value):
    if isinstance(value, unicode):
        return value
    return unicode(value)


def uprint(value):
    value = utext(value)
    if PY2:
        sys.stdout.write(value.encode("utf-8") + "\n")
    else:
        sys.stdout.write(value + "\n")
    sys.stdout.flush()


def abs_path(path):
    return os.path.abspath(os.path.expanduser(path))


def drive_letter(path):
    drive, tail = os.path.splitdrive(abs_path(path))
    return drive.lower()


def assert_not_c_drive(path, label):
    if drive_letter(path) == "c:":
        raise RuntimeError("%s must not be on C drive: %s" % (label, path))


def copy_folder_files(src_dir, dst_dir):
    copied = 0
    skipped = 0
    ensure_dir(dst_dir)
    for dirpath, dirnames, filenames in os.walk(src_dir):
        rel = os.path.relpath(dirpath, src_dir)
        out_dir = dst_dir if rel == "." else os.path.join(dst_dir, rel)
        ensure_dir(out_dir)
        for name in filenames:
            if name.lower().endswith(".lock"):
                skipped += 1
                continue
            src = os.path.join(dirpath, name)
            dst = os.path.join(out_dir, name)
            if os.path.exists(dst) and os.path.getsize(dst) == os.path.getsize(src):
                skipped += 1
                continue
            shutil.copy2(src, dst)
            copied += 1
    return copied, skipped


def copy_file_if_needed(src, dst):
    ensure_dir(os.path.dirname(dst))
    if os.path.exists(dst) and os.path.getsize(dst) == os.path.getsize(src):
        return False
    shutil.copy2(src, dst)
    return True


def safe_name(value):
    text = str(value)
    chars = []
    for char in text:
        if char.isalnum():
            chars.append(char.lower())
        else:
            chars.append("_")
    cleaned = "_".join([part for part in "".join(chars).split("_") if part])
    return cleaned or "band"


def scene_name_from_archive(path):
    name = os.path.basename(path)
    lower = name.lower()
    for suffix in [".tar.gz", ".tgz", ".tar"]:
        if lower.endswith(suffix):
            return name[:-len(suffix)]
    return os.path.splitext(name)[0]


def token_matches(name, token):
    return token.upper() in name.upper()


def any_band_matches(name, band_tokens):
    for token in band_tokens:
        if token_matches(name, token):
            return True
    return False


def find_source_files(source_dir):
    archives = []
    tifs = []
    for dirpath, dirnames, filenames in os.walk(source_dir):
        for name in filenames:
            lower = name.lower()
            path = os.path.join(dirpath, name)
            if lower.endswith((".tar", ".tar.gz", ".tgz")):
                archives.append(path)
            elif lower.endswith((".tif", ".tiff")):
                tifs.append(path)
    archives.sort()
    tifs.sort()
    return archives, tifs


def extract_selected_tifs(archive_path, output_root, band_tokens):
    scene_dir = os.path.join(output_root, scene_name_from_archive(archive_path))
    ensure_dir(scene_dir)
    extracted = []
    with tarfile.open(archive_path, "r:*") as archive:
        members = archive.getmembers()
        for member in members:
            if not member.isfile():
                continue
            basename = os.path.basename(member.name)
            lower = basename.lower()
            if not lower.endswith((".tif", ".tiff")):
                continue
            if not any_band_matches(basename, band_tokens):
                continue
            out_path = os.path.join(scene_dir, basename)
            source = archive.extractfile(member)
            if source is None:
                continue
            if os.path.exists(out_path) and os.path.getsize(out_path) == member.size:
                extracted.append(out_path)
                source.close()
                continue
            with open(out_path, "wb") as handle:
                shutil.copyfileobj(source, handle)
            source.close()
            extracted.append(out_path)
    return extracted


def collect_working_rasters(config, raw_remote_dir, manifest_path):
    source_dir = abs_path(config["remote_sensing_source_dir"])
    band_tokens = [str(token) for token in config.get("band_tokens", ["SR_B4", "SR_B3", "SR_B2"])]
    copy_archives = bool(config.get("copy_source_archives", False))
    copy_tifs = bool(config.get("copy_extracted_source_tifs", True))
    extract_archives = bool(config.get("extract_archives", True))
    extracted_dir = os.path.join(raw_remote_dir, "extracted_scenes")
    copied_tif_dir = os.path.join(raw_remote_dir, "source_tifs")
    archive_copy_dir = os.path.join(raw_remote_dir, "archives")
    ensure_dir(raw_remote_dir)
    ensure_dir(extracted_dir)

    archives, tifs = find_source_files(source_dir)
    selected_tifs = []
    manifest_lines = [
        u"Remote sensing source manifest",
        u"Source directory: %s" % source_dir,
        u"Band tokens: %s" % ", ".join(band_tokens),
        u"",
    ]

    for archive in archives:
        manifest_lines.append(u"Archive: %s" % archive)
        if copy_archives:
            dst = os.path.join(archive_copy_dir, os.path.basename(archive))
            copy_file_if_needed(archive, dst)
            manifest_lines.append(u"  Copied archive: %s" % dst)
        if extract_archives:
            uprint(u"Extracting selected bands from %s" % archive)
            extracted = extract_selected_tifs(archive, extracted_dir, band_tokens)
            selected_tifs.extend(extracted)
            for path in extracted:
                manifest_lines.append(u"  Extracted band: %s" % path)

    for tif in tifs:
        if not any_band_matches(os.path.basename(tif), band_tokens):
            continue
        if copy_tifs:
            dst = os.path.join(copied_tif_dir, os.path.basename(tif))
            copy_file_if_needed(tif, dst)
            selected_tifs.append(dst)
            manifest_lines.append(u"Copied source tif: %s" % dst)
        else:
            selected_tifs.append(tif)
            manifest_lines.append(u"Source tif: %s" % tif)

    with codecs.open(manifest_path, "w", "utf-8") as handle:
        handle.write(u"\n".join(manifest_lines))

    selected_tifs = sorted(set(selected_tifs))
    if not selected_tifs:
        raise RuntimeError("No matching remote-sensing raster bands found.")
    return selected_tifs, band_tokens


def group_rasters_by_band(paths, band_tokens):
    groups = {}
    for token in band_tokens:
        groups[token] = []
    for path in paths:
        name = os.path.basename(path)
        for token in band_tokens:
            if token_matches(name, token):
                groups[token].append(path)
                break
    missing = [token for token in band_tokens if not groups[token]]
    if missing:
        raise RuntimeError("No rasters found for band token(s): %s" % ", ".join(missing))
    for token in groups:
        groups[token].sort()
    return groups


def same_spatial_reference(source_sr, target_sr):
    if not source_sr or source_sr.name == "Unknown":
        raise RuntimeError("A source raster has no known spatial reference.")
    if source_sr.factoryCode and target_sr.factoryCode:
        return source_sr.factoryCode == target_sr.factoryCode
    return source_sr.name == target_sr.name


def build_nodata_condition(raster, nodata_values):
    condition = None
    for value in nodata_values:
        piece = raster == value
        condition = piece if condition is None else (condition | piece)
    return condition


def prepare_band_raster(arcpy, raster_path, token, index, target_sr, intermediate_dir, config, SetNull):
    desc = arcpy.Describe(raster_path)
    band_dir = os.path.join(intermediate_dir, "prepared_" + safe_name(token))
    ensure_dir(band_dir)
    base = safe_name(os.path.splitext(os.path.basename(raster_path))[0])
    working = raster_path

    if not same_spatial_reference(desc.spatialReference, target_sr):
        projected = os.path.join(band_dir, "%03d_%s_target_sr.tif" % (index, base))
        uprint(u"Projecting %s" % raster_path)
        arcpy.ProjectRaster_management(
            raster_path,
            projected,
            target_sr,
            config.get("resampling_type", "BILINEAR"),
            config.get("cell_size", "30")
        )
        working = projected

    nodata_values = [int(value) for value in config.get("nodata_values", [0])]
    if nodata_values:
        cleaned = os.path.join(band_dir, "%03d_%s_nodata.tif" % (index, base))
        uprint(u"Setting fill values to NoData: %s" % working)
        raster = arcpy.Raster(working)
        condition = build_nodata_condition(raster, nodata_values)
        SetNull(condition, raster).save(cleaned)
        working = cleaned

    return working


def mosaic_one_band(arcpy, rasters, token, target_sr, mosaic_dir, config):
    ensure_dir(mosaic_dir)
    output_name = "mosaic_%s.tif" % safe_name(token)
    uprint(u"Mosaicking band %s" % token)
    arcpy.MosaicToNewRaster_management(
        ";".join(rasters),
        mosaic_dir,
        output_name,
        target_sr,
        config.get("pixel_type", "16_BIT_UNSIGNED"),
        config.get("cell_size", "30"),
        "1",
        config.get("mosaic_method", "FIRST"),
        "FIRST"
    )
    return os.path.join(mosaic_dir, output_name)


def calculate_display_helpers(arcpy, raster_path, config):
    if bool(config.get("calculate_statistics", True)):
        try:
            arcpy.CalculateStatistics_management(raster_path)
        except Exception as exc:
            uprint(u"Warning: CalculateStatistics failed for %s: %s" % (raster_path, exc))
    if bool(config.get("build_pyramids", True)):
        try:
            arcpy.BuildPyramids_management(raster_path)
        except Exception as exc:
            uprint(u"Warning: BuildPyramids failed for %s: %s" % (raster_path, exc))


def save_raster_layer(arcpy, raster_path, chinese_name, layer_file):
    temp_name = "tmp_" + safe_name(os.path.splitext(os.path.basename(layer_file))[0])
    try:
        arcpy.Delete_management(temp_name)
    except Exception:
        pass
    arcpy.MakeRasterLayer_management(raster_path, temp_name)
    layer = arcpy.mapping.Layer(temp_name)
    layer.name = chinese_name
    arcpy.SaveToLayerFile_management(layer, layer_file, "ABSOLUTE")
    return arcpy.mapping.Layer(layer_file)


def save_boundary_layer(arcpy, boundary_path, layer_file):
    temp_name = "tmp_study_area_boundary"
    try:
        arcpy.Delete_management(temp_name)
    except Exception:
        pass
    arcpy.MakeFeatureLayer_management(boundary_path, temp_name)
    arcpy.SaveToLayerFile_management(temp_name, layer_file, "ABSOLUTE")
    layer = arcpy.mapping.Layer(layer_file)
    layer.name = u"研究区边界"
    arcpy.SaveToLayerFile_management(layer, layer_file, "ABSOLUTE")
    return arcpy.mapping.Layer(layer_file)


def expanded_extent(arcpy, extent, fraction):
    width = extent.XMax - extent.XMin
    height = extent.YMax - extent.YMin
    dx = width * fraction
    dy = height * fraction
    return arcpy.Extent(extent.XMin - dx, extent.YMin - dy, extent.XMax + dx, extent.YMax + dy)


def write_summary(path, target_sr, full_raster, clipped_raster, mxd_file, band_tokens, selected_count):
    with codecs.open(path, "w", "utf-8") as handle:
        handle.write(u"遥感影像拼接与裁剪处理结果\n")
        handle.write(u"目标坐标系: %s (EPSG:%s)\n" % (target_sr.name, target_sr.factoryCode))
        handle.write(u"波段顺序: %s\n" % ", ".join(band_tokens))
        handle.write(u"参与处理的栅格数量: %s\n" % selected_count)
        handle.write(u"完整拼接遥感影像: %s\n" % full_raster)
        handle.write(u"研究区裁剪遥感影像: %s\n" % clipped_raster)
        handle.write(u"ArcMap 工程: %s\n" % mxd_file)
        handle.write(u"ArcMap 中文图层名: 研究区边界; 研究区遥感影像（裁剪结果）; 完整遥感影像（拼接结果）\n")


def unique_destination(path):
    if not os.path.exists(path):
        return path
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = path + "_" + stamp
    index = 2
    while os.path.exists(candidate):
        candidate = path + "_" + stamp + "_%s" % index
        index += 1
    return candidate


def move_if_exists(src, dst):
    if not os.path.exists(src):
        return None
    ensure_dir(os.path.dirname(dst))
    final_dst = unique_destination(dst)
    shutil.move(src, final_dst)
    return final_dst


def organize_deletable_outputs(config, project_root, raw_dir, intermediate_dir, scratch_dir):
    if not bool(config.get("organize_deletable_outputs", False)):
        return []
    delete_folder = config.get("delete_folder")
    if not delete_folder:
        delete_folder = os.path.join(os.path.dirname(project_root), u"可以删除")
    delete_folder = abs_path(delete_folder)
    assert_not_c_drive(delete_folder, "delete_folder")
    ensure_dir(delete_folder)

    moved = []
    targets = [
        (raw_dir, u"01_原始数据副本和解压波段_可以删除"),
        (intermediate_dir, u"02_中间镶嵌处理文件_可以删除"),
        (scratch_dir, u"03_ArcGIS临时文件_可以删除"),
    ]
    for src, name in targets:
        try:
            dst = os.path.join(delete_folder, name)
            moved_to = move_if_exists(src, dst)
            if moved_to:
                moved.append((src, moved_to))
                uprint(u"Moved re-creatable files to: %s" % moved_to)
        except Exception as exc:
            uprint(u"Warning: could not move %s into delete folder: %s" % (src, exc))
    return moved


def main():
    parser = argparse.ArgumentParser(description="Mosaic remote-sensing scenes and clip by a study-area shapefile with ArcGIS 10.x.")
    parser.add_argument("--config", required=True, help="Path to JSON config.")
    args = parser.parse_args()

    config = load_json(args.config)
    project_root = abs_path(config["project_root"])
    source_dir = abs_path(config["remote_sensing_source_dir"])
    study_area_shp = abs_path(config["study_area_shp"])
    output_prefix = config.get("output_prefix", "remote_sensing")
    template_mxd = abs_path(config["arcmap_template_mxd"])

    assert_not_c_drive(project_root, "project_root")
    assert_not_c_drive(source_dir, "remote_sensing_source_dir")
    assert_not_c_drive(study_area_shp, "study_area_shp")
    if not os.path.isdir(source_dir):
        raise RuntimeError("Remote-sensing source directory does not exist: %s" % source_dir)
    if not os.path.exists(study_area_shp):
        raise RuntimeError("Study-area shapefile does not exist: %s" % study_area_shp)
    if not os.path.exists(template_mxd):
        raise RuntimeError("ArcMap template MXD does not exist: %s" % template_mxd)

    raw_dir = os.path.join(project_root, "00_original_data")
    raw_remote_dir = os.path.join(raw_dir, "remote_sensing")
    raw_boundary_dir = os.path.join(raw_dir, "study_area_boundary")
    intermediate_dir = os.path.join(project_root, "01_intermediate")
    output_dir = os.path.join(project_root, "02_outputs")
    arcmap_dir = os.path.join(project_root, "03_arcmap")
    scratch_dir = os.path.join(project_root, "_scratch")

    for label, path in [
        ("raw_dir", raw_dir),
        ("intermediate_dir", intermediate_dir),
        ("output_dir", output_dir),
        ("arcmap_dir", arcmap_dir),
        ("scratch_dir", scratch_dir),
    ]:
        assert_not_c_drive(path, label)
        ensure_dir(path)

    os.environ["TEMP"] = scratch_dir
    os.environ["TMP"] = scratch_dir
    os.environ["ARCTMPDIR"] = scratch_dir

    import arcpy
    from arcpy.sa import ExtractByMask, SetNull

    arcpy.env.overwriteOutput = True
    arcpy.env.workspace = intermediate_dir
    arcpy.env.scratchWorkspace = scratch_dir
    try:
        arcpy.SetLogHistory(False)
    except Exception:
        pass

    if arcpy.CheckExtension("Spatial") != "Available":
        raise RuntimeError("Spatial Analyst extension is required.")
    arcpy.CheckOutExtension("Spatial")

    if bool(config.get("copy_boundary", True)):
        uprint(u"Organizing study-area boundary files")
        copy_folder_files(os.path.dirname(study_area_shp), raw_boundary_dir)
        boundary = os.path.join(raw_boundary_dir, os.path.basename(study_area_shp))
    else:
        boundary = study_area_shp

    target_sr = arcpy.Describe(boundary).spatialReference
    if not target_sr or target_sr.name == "Unknown":
        raise RuntimeError("Study-area shapefile has no known spatial reference.")

    manifest_path = os.path.join(raw_remote_dir, "source_manifest.txt")
    selected_rasters, band_tokens = collect_working_rasters(config, raw_remote_dir, manifest_path)
    groups = group_rasters_by_band(selected_rasters, band_tokens)

    mosaic_dir = os.path.join(intermediate_dir, "band_mosaics")
    band_mosaics = []
    for token in band_tokens:
        prepared = []
        for index, raster_path in enumerate(groups[token], 1):
            prepared.append(prepare_band_raster(arcpy, raster_path, token, index, target_sr, intermediate_dir, config, SetNull))
        band_mosaics.append(mosaic_one_band(arcpy, prepared, token, target_sr, mosaic_dir, config))

    full_raster = os.path.join(output_dir, output_prefix + "_full_mosaic.tif")
    clipped_raster = os.path.join(output_dir, output_prefix + "_study_area_clip.tif")
    boundary_line = os.path.join(output_dir, "study_area_boundary_outline.shp")
    summary_file = os.path.join(output_dir, output_prefix + "_summary_cn.txt")
    mxd_file = os.path.join(arcmap_dir, output_prefix + "_arcmap.mxd")
    full_lyr = os.path.join(arcmap_dir, output_prefix + "_full_mosaic_cn.lyr")
    clipped_lyr = os.path.join(arcmap_dir, output_prefix + "_study_area_clip_cn.lyr")
    boundary_lyr = os.path.join(arcmap_dir, "study_area_boundary_cn.lyr")

    uprint(u"Compositing bands into complete remote-sensing image")
    arcpy.CompositeBands_management(";".join(band_mosaics), full_raster)
    calculate_display_helpers(arcpy, full_raster, config)

    uprint(u"Clipping complete image by study-area boundary")
    arcpy.env.snapRaster = band_mosaics[0]
    arcpy.env.cellSize = config.get("cell_size", "30")
    try:
        ExtractByMask(full_raster, boundary).save(clipped_raster)
    except Exception as exc:
        uprint(u"Warning: ExtractByMask failed, using Clip_management with clipping geometry: %s" % exc)
        arcpy.Clip_management(full_raster, "#", clipped_raster, boundary, "#", "ClippingGeometry", "MAINTAIN_EXTENT")
    calculate_display_helpers(arcpy, clipped_raster, config)

    uprint(u"Creating ArcMap layers and MXD")
    arcpy.FeatureToLine_management(boundary, boundary_line)
    full_layer = save_raster_layer(arcpy, full_raster, u"完整遥感影像（拼接结果）", full_lyr)
    clipped_layer = save_raster_layer(arcpy, clipped_raster, u"研究区遥感影像（裁剪结果）", clipped_lyr)
    boundary_layer = save_boundary_layer(arcpy, boundary_line, boundary_lyr)

    shutil.copy2(template_mxd, mxd_file)
    mxd = arcpy.mapping.MapDocument(mxd_file)
    df = arcpy.mapping.ListDataFrames(mxd)[0]
    df.spatialReference = target_sr
    for old_layer in arcpy.mapping.ListLayers(mxd, "", df):
        arcpy.mapping.RemoveLayer(df, old_layer)
    arcpy.mapping.AddLayer(df, full_layer, "BOTTOM")
    arcpy.mapping.AddLayer(df, clipped_layer, "TOP")
    arcpy.mapping.AddLayer(df, boundary_layer, "TOP")
    df.extent = expanded_extent(arcpy, arcpy.Describe(boundary_line).extent, 0.08)
    mxd.activeView = df.name
    mxd.save()
    del mxd

    write_summary(summary_file, target_sr, full_raster, clipped_raster, mxd_file, band_tokens, len(selected_rasters))
    arcpy.CheckInExtension("Spatial")
    organize_deletable_outputs(config, project_root, raw_dir, intermediate_dir, scratch_dir)
    uprint(u"Done: %s" % mxd_file)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        try:
            import arcpy
            arcpy.CheckInExtension("Spatial")
        except Exception:
            pass
        sys.exit(1)
