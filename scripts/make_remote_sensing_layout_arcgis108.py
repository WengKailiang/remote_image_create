# -*- coding: utf-8 -*-
from __future__ import division

import codecs
import json
import math
import os
import struct
import sys

import arcpy
import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import patches
from matplotlib.font_manager import FontProperties


def to_unicode(value):
    if isinstance(value, unicode):
        return value
    return value.decode("mbcs")


def ensure_dir(path):
    if not os.path.isdir(path):
        os.makedirs(path)


def font_prop(paths, size):
    for path in paths:
        if os.path.exists(path):
            return FontProperties(fname=path, size=size)
    return FontProperties(size=size)


FONT_CN = font_prop(
    [
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\msyh.ttc",
    ],
    13,
)
FONT_EN = font_prop(
    [
        r"C:\Windows\Fonts\times.ttf",
        r"C:\Windows\Fonts\timesbd.ttf",
    ],
    13,
)


def raster_info(path):
    desc = arcpy.Describe(path)
    cell_x = float(arcpy.GetRasterProperties_management(path, "CELLSIZEX").getOutput(0))
    cell_y = float(arcpy.GetRasterProperties_management(path, "CELLSIZEY").getOutput(0))
    cols = int(arcpy.GetRasterProperties_management(path, "COLUMNCOUNT").getOutput(0))
    rows = int(arcpy.GetRasterProperties_management(path, "ROWCOUNT").getOutput(0))
    return desc, cell_x, cell_y, cols, rows


def fs_path(path):
    if isinstance(path, unicode):
        return path.encode("mbcs")
    return path


def read_shp_parts(path):
    parts_out = []
    xmin = ymin = float("inf")
    xmax = ymax = float("-inf")
    with open(fs_path(path), "rb") as handle:
        handle.seek(100)
        while True:
            record_header = handle.read(8)
            if len(record_header) < 8:
                break
            record_number, content_words = struct.unpack(">2i", record_header)
            content = handle.read(content_words * 2)
            if len(content) < 44:
                continue
            shape_type = struct.unpack("<i", content[:4])[0]
            if shape_type not in (3, 5, 13, 15, 23, 25):
                continue
            box = struct.unpack("<4d", content[4:36])
            xmin = min(xmin, box[0])
            ymin = min(ymin, box[1])
            xmax = max(xmax, box[2])
            ymax = max(ymax, box[3])
            num_parts, num_points = struct.unpack("<2i", content[36:44])
            parts = struct.unpack("<%di" % num_parts, content[44 : 44 + 4 * num_parts])
            point_offset = 44 + 4 * num_parts
            raw_points = struct.unpack("<%dd" % (num_points * 2), content[point_offset : point_offset + 16 * num_points])
            points = [(raw_points[i], raw_points[i + 1]) for i in range(0, len(raw_points), 2)]
            for idx, start in enumerate(parts):
                end = parts[idx + 1] if idx + 1 < len(parts) else len(points)
                parts_out.append(points[start:end])
    if not parts_out:
        raise RuntimeError("No polygon/polyline geometry found in shapefile: %s" % path)
    return parts_out, (xmin, ymin, xmax, ymax)


def read_point_shp(path):
    points = []
    with open(fs_path(path), "rb") as handle:
        handle.seek(100)
        while True:
            record_header = handle.read(8)
            if len(record_header) < 8:
                break
            record_number, content_words = struct.unpack(">2i", record_header)
            content = handle.read(content_words * 2)
            if len(content) < 20:
                continue
            shape_type = struct.unpack("<i", content[:4])[0]
            if shape_type in (1, 11, 21):
                points.append(struct.unpack("<2d", content[4:20]))
    return points


def read_hydropower_csv(path, out_sr):
    rows = []
    with codecs.open(path, "r", "utf-8-sig") as handle:
        lines = [line.strip() for line in handle.readlines() if line.strip()]
    if not lines:
        return []
    header = [item.strip() for item in lines[0].split(",")]
    for line in lines[1:]:
        values = [item.strip() for item in line.split(",")]
        rows.append(dict(zip(header, values)))
    if not rows:
        return []
    lower = dict((key.lower(), key) for key in header)
    lon_key = lower.get("longitude") or lower.get("lon") or lower.get("经度")
    lat_key = lower.get("latitude") or lower.get("lat") or lower.get("纬度")
    if not lon_key or not lat_key:
        raise RuntimeError("Hydropower CSV must contain Longitude/Latitude columns: %s" % path)
    points = []
    for row in rows:
        lon = float(row[lon_key])
        lat = float(row[lat_key])
        points.append(project_lonlat(lon, lat, out_sr))
    return points


def stretch_rgb(arr, brighten=1.0):
    arr = arr.astype("float32")
    if arr.ndim == 2:
        arr = arr[np.newaxis, :, :]
    if arr.shape[0] > 3:
        arr = arr[:3, :, :]
    rgb = np.zeros((arr.shape[1], arr.shape[2], 3), dtype="float32")
    valid_any = np.zeros((arr.shape[1], arr.shape[2]), dtype=bool)
    for idx in range(3):
        band = arr[idx, :, :]
        valid = band > 0
        valid_any |= valid
        if np.any(valid):
            sample = band[valid]
            lo = np.percentile(sample, 2)
            hi = np.percentile(sample, 98)
            if hi <= lo:
                lo = float(sample.min())
                hi = float(sample.max())
            if hi <= lo:
                hi = lo + 1.0
            rgb[:, :, idx] = np.clip((band - lo) / (hi - lo), 0, 1)
    rgb = np.clip(rgb * brighten, 0, 1)
    alpha = valid_any.astype("float32")
    rgba = np.dstack([rgb, alpha])
    return rgba


def read_raster_window(path, extent):
    desc, cell_x, cell_y, cols, rows = raster_info(path)
    raster_extent = desc.extent
    xmin = max(extent[0], raster_extent.XMin)
    ymin = max(extent[1], raster_extent.YMin)
    xmax = min(extent[2], raster_extent.XMax)
    ymax = min(extent[3], raster_extent.YMax)
    ncols = int(math.ceil((xmax - xmin) / cell_x))
    nrows = int(math.ceil((ymax - ymin) / abs(cell_y)))
    arr = arcpy.RasterToNumPyArray(path, arcpy.Point(xmin, ymin), ncols, nrows, 0)
    return arr, (xmin, xmax, ymin, ymax)


def read_full_raster(path):
    desc, cell_x, cell_y, cols, rows = raster_info(path)
    arr = arcpy.RasterToNumPyArray(path, nodata_to_value=0)
    return arr, (desc.extent.XMin, desc.extent.XMax, desc.extent.YMin, desc.extent.YMax)


def project_lonlat(lon, lat, out_sr):
    wgs84 = arcpy.SpatialReference(4326)
    point = arcpy.PointGeometry(arcpy.Point(lon, lat), wgs84).projectAs(out_sr).firstPoint
    return point.X, point.Y


def project_xy_to_lonlat(x, y, in_sr):
    wgs84 = arcpy.SpatialReference(4326)
    point = arcpy.PointGeometry(arcpy.Point(x, y), in_sr).projectAs(wgs84).firstPoint
    return point.X, point.Y


def dms_label(value, axis):
    hemi = "E" if axis == "lon" and value >= 0 else "W" if axis == "lon" else "N" if value >= 0 else "S"
    value = abs(value)
    degree = int(math.floor(value))
    minutes_total = (value - degree) * 60.0
    minute = int(math.floor(minutes_total + 1e-8))
    second = int(round((minutes_total - minute) * 60.0))
    if second == 60:
        second = 0
        minute += 1
    if minute == 60:
        minute = 0
        degree += 1
    return u"%d°%d'0\"%s" % (degree, minute, hemi)


def nice_ticks(min_value, max_value, step_minutes=5):
    step = step_minutes / 60.0
    start = math.ceil((min_value - 1e-10) / step) * step
    ticks = []
    value = start
    while value <= max_value + 1e-10:
        ticks.append(round(value, 10))
        value += step
    return ticks


def draw_boundary(ax, boundary_parts):
    for part in boundary_parts:
        if not part:
            continue
        xs = [point[0] for point in part]
        ys = [point[1] for point in part]
        ax.plot(xs, ys, color="0.25", linewidth=5.2, alpha=0.85, zorder=8)
        ax.plot(xs, ys, color="white", linewidth=3.1, zorder=9)


def draw_north_arrow(fig):
    box = fig.add_axes([0.105, 0.765, 0.15, 0.15])
    if hasattr(box, "set_facecolor"):
        box.set_facecolor("white")
    else:
        box.set_axis_bgcolor("white")
    for spine in box.spines.values():
        spine.set_color("black")
        spine.set_linewidth(1.0)
    box.set_xticks([])
    box.set_yticks([])
    box.set_xlim(0, 1)
    box.set_ylim(0, 1)
    cx, cy = 0.5, 0.52
    triangles = [
        ([(cx, 0.82), (0.44, cy), (0.56, cy)], "black"),
        ([(cx, 0.24), (0.44, cy), (0.56, cy)], "white"),
        ([(0.20, cy), (cx, 0.46), (cx, 0.58)], "white"),
        ([(0.80, cy), (cx, 0.46), (cx, 0.58)], "black"),
    ]
    for coords, face in triangles:
        box.add_patch(patches.Polygon(coords, closed=True, facecolor=face, edgecolor="black", linewidth=0.9))
    box.text(0.5, 0.97, "N", ha="center", va="top", fontproperties=FONT_EN, fontsize=15)
    box.text(0.5, 0.08, "S", ha="center", va="bottom", fontproperties=FONT_EN, fontsize=15)
    box.text(0.07, 0.50, "W", ha="left", va="center", fontproperties=FONT_EN, fontsize=15)
    box.text(0.93, 0.50, "E", ha="right", va="center", fontproperties=FONT_EN, fontsize=15)


def draw_scale_bar(ax, extent):
    xmin, ymin, xmax, ymax = extent
    bar_len = 8000.0
    segment_lengths = [2000.0, 2000.0, 4000.0]
    height = (ymax - ymin) * 0.012
    x0 = xmax - bar_len - (xmax - xmin) * 0.135
    y0 = ymin + (ymax - ymin) * 0.055
    pad_x = (xmax - xmin) * 0.018
    pad_y = (ymax - ymin) * 0.020
    ax.add_patch(
        patches.Rectangle(
            (x0 - pad_x, y0 - pad_y),
            bar_len + pad_x * 6.20,
            height + pad_y * 3.0,
            facecolor="white",
            edgecolor="black",
            linewidth=0.8,
            zorder=20,
        )
    )
    cursor = x0
    colors = ["black", "white", "black"]
    for length, color in zip(segment_lengths, colors):
        ax.add_patch(
            patches.Rectangle(
                (cursor, y0),
                length,
                height,
                facecolor=color,
                edgecolor="black",
                linewidth=0.7,
                zorder=21,
            )
        )
        cursor += length
    label_y = y0 + height + pad_y * 0.35
    for label, xpos in [("0", x0), ("2", x0 + 2000), ("4", x0 + 4000), ("8", x0 + 8000)]:
        ax.text(xpos, label_y, label, ha="center", va="bottom", fontproperties=FONT_EN, fontsize=13, zorder=22)
    ax.text(x0 + bar_len + pad_x * 0.85, y0 + height * 0.50, "Km", ha="left", va="center", fontproperties=FONT_EN, fontsize=14, zorder=22)


def draw_legend(ax, extent, has_hydropower=True, has_landslide=True):
    xmin, ymin, xmax, ymax = extent
    w = (xmax - xmin) * 0.22
    h = (ymax - ymin) * 0.090
    x0 = xmin + (xmax - xmin) * 0.03
    y0 = ymin + (ymax - ymin) * 0.045
    ax.add_patch(patches.Rectangle((x0, y0), w, h, facecolor="white", edgecolor="black", linewidth=0.8, zorder=20))
    y_top = y0 + h * 0.68
    y_bottom = y0 + h * 0.30
    if has_hydropower:
        ax.scatter([x0 + w * 0.16], [y_top], marker="*", s=180, c="red", edgecolors="black", linewidths=0.8, zorder=22)
        ax.text(x0 + w * 0.34, y_top, u"水电站", ha="left", va="center", fontproperties=FONT_CN, fontsize=13, zorder=22)
    if has_landslide:
        ax.scatter([x0 + w * 0.16], [y_bottom], marker="^", s=95, c="red", edgecolors="red", linewidths=0.6, zorder=22)
        ax.text(x0 + w * 0.34, y_bottom, u"滑坡点", ha="left", va="center", fontproperties=FONT_CN, fontsize=13, zorder=22)


def main():
    cfg_path = to_unicode(sys.argv[1])
    out_dir = to_unicode(sys.argv[2])
    ensure_dir(out_dir)
    with codecs.open(cfg_path, "r", "utf-8") as handle:
        cfg = json.load(handle)

    project_root = cfg["project_root"]
    outputs = os.path.join(project_root, "02_outputs")
    full_raster = os.path.join(outputs, cfg["output_prefix"] + "_full_mosaic.tif")
    clip_raster = os.path.join(outputs, cfg["output_prefix"] + "_study_area_clip.tif")
    boundary = os.path.join(outputs, "study_area_boundary_outline.shp")
    package_root = os.path.dirname(cfg_path)
    point_dir = os.path.join(package_root, u"原始数据", u"滑坡点与水电站位置")
    landslide_shp = os.path.join(point_dir, "landslide_points.shp")
    hydropower_csv = os.path.join(point_dir, u"倾泻点.csv")

    full_desc = arcpy.Describe(full_raster)
    sr = full_desc.spatialReference
    boundary_parts, boundary_extent = read_shp_parts(boundary)
    landslide_points = read_point_shp(landslide_shp) if os.path.exists(fs_path(landslide_shp)) else []
    hydropower_points = read_hydropower_csv(hydropower_csv, sr) if os.path.exists(fs_path(hydropower_csv)) else []
    width = boundary_extent[2] - boundary_extent[0]
    height = boundary_extent[3] - boundary_extent[1]
    side = max(width, height) * 1.48
    cx = (boundary_extent[0] + boundary_extent[2]) / 2.0
    cy = (boundary_extent[1] + boundary_extent[3]) / 2.0
    map_extent = [cx - side / 2.0, cy - side / 2.0, cx + side / 2.0, cy + side / 2.0]

    full_arr, full_extent = read_raster_window(full_raster, map_extent)
    clip_arr, clip_extent = read_full_raster(clip_raster)
    full_rgba = stretch_rgb(full_arr, brighten=1.22)
    full_rgba[:, :, 3] *= 0.62
    clip_rgba = stretch_rgb(clip_arr, brighten=1.05)
    clip_rgba[:, :, 3] *= 0.98

    fig = plt.figure(figsize=(8.2, 8.2), dpi=300)
    ax = fig.add_axes([0.08, 0.08, 0.84, 0.84])
    ax.imshow(full_rgba, extent=full_extent, origin="upper", zorder=1)
    ax.imshow(clip_rgba, extent=clip_extent, origin="upper", zorder=5)
    draw_boundary(ax, boundary_parts)
    if landslide_points:
        ax.scatter(
            [point[0] for point in landslide_points],
            [point[1] for point in landslide_points],
            marker="^",
            s=16,
            c="red",
            edgecolors="red",
            linewidths=0.25,
            zorder=12,
        )
    if hydropower_points:
        ax.scatter(
            [point[0] for point in hydropower_points],
            [point[1] for point in hydropower_points],
            marker="*",
            s=230,
            c="red",
            edgecolors="black",
            linewidths=0.8,
            zorder=13,
        )

    ax.set_xlim(map_extent[0], map_extent[2])
    ax.set_ylim(map_extent[1], map_extent[3])
    ax.set_aspect("equal")

    lonlat_corners = [project_xy_to_lonlat(x, y, sr) for x in [map_extent[0], map_extent[2]] for y in [map_extent[1], map_extent[3]]]
    min_lon = min(v[0] for v in lonlat_corners)
    max_lon = max(v[0] for v in lonlat_corners)
    min_lat = min(v[1] for v in lonlat_corners)
    max_lat = max(v[1] for v in lonlat_corners)
    lon_ticks = nice_ticks(min_lon, max_lon, 5)
    lat_ticks = nice_ticks(min_lat, max_lat, 5)
    x_ticks = [project_lonlat(lon, min_lat, sr)[0] for lon in lon_ticks]
    y_ticks = [project_lonlat(min_lon, lat, sr)[1] for lat in lat_ticks]
    ax.set_xticks(x_ticks)
    ax.set_yticks(y_ticks)
    ax.set_xticklabels([dms_label(lon, "lon") for lon in lon_ticks], fontproperties=FONT_EN, fontsize=13)
    ax.set_yticklabels([dms_label(lat, "lat") for lat in lat_ticks], fontproperties=FONT_EN, fontsize=13)
    ax.tick_params(axis="both", which="major", top=True, bottom=True, left=True, right=True, labeltop=True, labelbottom=True, labelleft=True, labelright=True, direction="out", length=5.5, width=1.0, pad=3)
    for label in ax.get_yticklabels():
        label.set_rotation(90)
        label.set_va("center")
    for spine in ax.spines.values():
        spine.set_linewidth(1.8)
        spine.set_color("black")

    draw_north_arrow(fig)
    draw_scale_bar(ax, map_extent)
    draw_legend(ax, map_extent, bool(hydropower_points), bool(landslide_points))

    png_path = os.path.join(out_dir, cfg["output_prefix"] + "_layout_map.png")
    fig.savefig(png_path, dpi=300)
    plt.close(fig)
    print("PNG=%s" % png_path.encode("utf-8"))
    print("LANDSLIDE_POINTS=%s" % len(landslide_points))
    print("HYDROPOWER_POINTS=%s" % len(hydropower_points))


if __name__ == "__main__":
    main()
