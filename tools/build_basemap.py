"""Build the web app's basemaps: terrain heightmaps and projected outlines.

  docs/data/<metro>/ : extent fitted to the metro (Springfield: 240 x 220 km, 0.25 km/px); tracts, counties,
                       state lines and town labels (TIGER incorporated places).
  docs/data/nation/  : conterminous US, 4 km/px, state outlines, for out-of-state flows.

Terrain comes from AWS Terrain Tiles (terrarium encoding; SRTM/GMTED/NED). It is stored as 16-bit
elevation (+500 m offset) in R/G with a land mask in B, the same encoding as the
European_spatiotemporal_geography atlas.
Coordinates are spherical Lambert azimuthal equal-area, in km, one centre per scale.

Usage: python tools/build_basemap.py --raw <cache dir> [nation] [metro ...]
"""
import argparse
import io
import json
import math
import os
import sys
import urllib.request

import pandas as pd

import geopandas as gpd
import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import median_filter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "data")
R = 6371.0
TILES = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
SCALES = {"nation": dict(lon0=-96.0, lat0=38.0, extent=[-2450, -1650, 2350, 1600], kmpx=4.0, z=6)}


def laea(lon, lat, lon0, lat0):
    lon, lat, l0, p0 = map(np.radians, (lon, lat, lon0, lat0))
    k = np.sqrt(2 / (1 + np.sin(p0) * np.sin(lat) + np.cos(p0) * np.cos(lat) * np.cos(lon - l0)))
    return R * k * np.cos(lat) * np.sin(lon - l0), R * k * (np.cos(p0) * np.sin(lat) - np.sin(p0) * np.cos(lat) * np.cos(lon - l0))


def laea_inv(x, y, lon0, lat0):
    l0, p0 = math.radians(lon0), math.radians(lat0)
    rho = np.hypot(x, y)
    c = 2 * np.arcsin(np.clip(rho / (2 * R), -1, 1))
    with np.errstate(invalid="ignore", divide="ignore"):
        lat = np.arcsin(np.cos(c) * math.sin(p0) + np.where(rho == 0, 0, y * np.sin(c) * math.cos(p0) / rho))
        lon = l0 + np.arctan2(x * np.sin(c), rho * math.cos(p0) * np.cos(c) - y * math.sin(p0) * np.sin(c))
    return np.degrees(lon), np.degrees(lat)


def fetch(url, cache):
    if os.path.exists(cache):
        return open(cache, "rb").read()
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    data = urllib.request.urlopen(url, timeout=60).read()
    open(cache, "wb").write(data)
    return data


def terrain(sc, raw, land_polys=None):
    xmin, ymin, xmax, ymax = sc["extent"]; k = sc["kmpx"]; z = sc["z"]
    w, h = int((xmax - xmin) / k), int((ymax - ymin) / k)
    gx, gy = np.meshgrid(xmin + (np.arange(w) + .5) * k, ymax - (np.arange(h) + .5) * k)
    lon, lat = laea_inv(gx, gy, sc["lon0"], sc["lat0"])
    n = 2 ** z
    px = (lon + 180) / 360 * n * 256
    py = (1 - np.arcsinh(np.tan(np.radians(lat))) / math.pi) / 2 * n * 256
    tx0, tx1, ty0, ty1 = int(px.min() // 256), int(px.max() // 256), int(py.min() // 256), int(py.max() // 256)
    mos = np.zeros(((ty1 - ty0 + 1) * 256, (tx1 - tx0 + 1) * 256), np.float32)
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            a = np.asarray(Image.open(io.BytesIO(fetch(TILES.format(z=z, x=tx, y=ty),
                                                         os.path.join(raw, "tiles", f"{z}_{tx}_{ty}.png")))).convert("RGB"), np.float32)
            mos[(ty - ty0) * 256:(ty - ty0 + 1) * 256, (tx - tx0) * 256:(tx - tx0 + 1) * 256] = a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768
    mx, my = px - tx0 * 256 - .5, py - ty0 * 256 - .5
    x0 = np.clip(np.floor(mx).astype(int), 0, mos.shape[1] - 2); y0 = np.clip(np.floor(my).astype(int), 0, mos.shape[0] - 2)
    fx, fy = np.clip(mx - x0, 0, 1), np.clip(my - y0, 0, 1)
    e = (mos[y0, x0] * (1 - fx) * (1 - fy) + mos[y0, x0 + 1] * fx * (1 - fy) + mos[y0 + 1, x0] * (1 - fx) * fy + mos[y0 + 1, x0 + 1] * fx * fy)
    # despike: terrarium tiles carry a few nodata/void pixels; replace outliers with the 5x5 median
    lo_, hi_ = np.percentile(e, [0.02, 99.98])
    bad = (e < lo_) | (e > hi_)
    e = np.where(bad, median_filter(np.clip(e, lo_, hi_), size=5), e)
    land = np.ones((h, w), bool)
    if land_polys is not None:
        m = Image.new("L", (w, h), 0); d = ImageDraw.Draw(m)
        for ring in land_polys:
            d.polygon([((x - xmin) / k, (ymax - y) / k) for x, y in ring], fill=255)
        land = np.asarray(m) > 0
    v = np.clip(np.round(e + 500), 0, 65535).astype(np.uint32)
    img = Image.fromarray(np.stack([(v >> 8) & 255, v & 255, np.where(land, 255, 0)], -1).astype(np.uint8), "RGB")
    return img, (w, h), float(e[land].min()), float(e[land].max())


def rings(geom, sc, tol):
    g = geom.simplify(tol)
    polys = [g] if g.geom_type == "Polygon" else list(g.geoms)
    out = []
    for p in polys:
        x, y = laea(*np.asarray(p.exterior.coords).T, sc["lon0"], sc["lat0"])
        out.append([[round(a, 2), round(b, 2)] for a, b in zip(x, y)])
    return out


def metro_scale(metro, tr_ll):
    """Extent fitted to the metro's tracts: square-ish, 35 % margin, >= 100 km half-width; ~1000 px wide."""
    if metro == "springfield":                     # keep the original framing
        return dict(lon0=-93.10, lat0=37.30, extent=[-120, -110, 120, 110], kmpx=0.25, z=10)
    x0, y0, x1, y1 = tr_ll.total_bounds
    lon0, lat0 = round((x0 + x1) / 2, 3), round((y0 + y1) / 2, 3)
    px, py = [], []
    for g in tr_ll.geometry:
        polys = [g] if g.geom_type == "Polygon" else list(g.geoms)
        for p in polys:
            x, y = laea(*np.asarray(p.exterior.coords).T, lon0, lat0); px += list(x); py += list(y)
    hx = max(100, 1.35 * max(abs(min(px)), abs(max(px))) + 20)
    hy = max(90, 1.35 * max(abs(min(py)), abs(max(py))) + 20)
    kmpx = round(2 * max(hx, hy) / 1000, 3)
    z = int(np.clip(round(math.log2(40075 * math.cos(math.radians(lat0)) / (256 * kmpx))), 6, 11))
    return dict(lon0=lon0, lat0=lat0, extent=[-round(hx), -round(hy), round(hx), round(hy)], kmpx=kmpx, z=z)


def build_metro(metro, raw):
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from config import metro_def, STATE_FIPS
    M = metro_def(metro); C = set(M["counties"])
    tiger = os.path.join(ROOT, "Data", "tiger")
    tr = pd.concat([gpd.read_file(os.path.join(tiger, f"tl_2020_{STATE_FIPS[s]}_tract.shp")) for s in M["states"]], ignore_index=True)
    tr = tr[(tr.STATEFP + tr.COUNTYFP).isin(C)].to_crs(4326)
    m = metro_scale(metro, tr)
    out = os.path.join(OUT, metro); os.makedirs(out, exist_ok=True)
    img, size, lo, hi = terrain(m, raw)
    img.save(os.path.join(out, "terrain.png"), optimize=True)
    cty = gpd.read_file(os.path.join(raw, "cb_2020_us_county_20m")).to_crs(4326)
    bx, by = laea_inv(np.array([m["extent"][0], m["extent"][2]]), np.array([m["extent"][1], m["extent"][3]]), m["lon0"], m["lat0"])
    cm = cty.cx[bx.min() - .3:bx.max() + .3, by.min() - .3:by.max() + .3]
    st_all = gpd.read_file(os.path.join(raw, "cb_2020_us_state_20m")).to_crs(4326)
    sm_ = st_all.cx[bx.min() - .3:bx.max() + .3, by.min() - .3:by.max() + .3]
    # town labels: incorporated places inside the extent, the 18 with most 2024 private jobs (LODES main files)
    import duckdb
    from config import PARQUET
    pls = []
    for f in sorted(os.listdir(tiger)):
        if f.endswith("_place.shp"):
            pls.append(gpd.read_file(os.path.join(tiger, f)))
    pl = pd.concat(pls, ignore_index=True)
    pl = pl[pl.CLASSFP.str.startswith("C")].copy()
    pl["lon"], pl["lat"] = pl.INTPTLON.astype(float), pl.INTPTLAT.astype(float)
    x, y = laea(pl.lon.values, pl.lat.values, m["lon0"], m["lat0"])
    ex = m["extent"]; pl["x"], pl["y"] = x, y
    pl = pl[(x > ex[0] * 0.95) & (x < ex[2] * 0.95) & (y > ex[1] * 0.95) & (y < ex[3] * 0.95)]
    q = " UNION ALL ".join(f"""SELECT x.stplc, sum(o.S000) jobs FROM '{PARQUET / s / 'od' / f'{s}_od_main_JT02_2024.parquet'}' o
                               JOIN '{PARQUET / s / f'{s}_xwalk.parquet'}' x ON o.w_geocode = x.tabblk2020 GROUP BY 1"""
                           for s in STATE_FIPS if (PARQUET / s / 'od' / f'{s}_od_main_JT02_2024.parquet').exists())
    jobs = duckdb.sql(q).df().groupby("stplc").jobs.sum()
    pl["jobs"] = pl.GEOID.map(jobs).fillna(0)
    pl = pl.sort_values("jobs", ascending=False).drop_duplicates("NAME").head(18)
    geo = {
        "tracts": [{"id": r.GEOID, "rings": rings(r.geometry, m, 0.0003)} for r in tr.itertuples()],
        "counties": [{"id": r.GEOID, "name": r.NAME, "msa": r.GEOID in C, "rings": rings(r.geometry, m, 0.001)} for r in cm.itertuples()],
        "states": [{"id": r.STATEFP, "abbr": r.STUSPS, "rings": rings(r.geometry, m, 0.002)} for r in sm_.itertuples()],
        "places": [{"name": r.NAME, "xy": [round(r.x, 2), round(r.y, 2)]} for r in pl.itertuples()],
    }
    meta = {"R": R, "elevOffset": 500, "metro": {**m, "size": size, "elevMin": lo, "elevMax": hi}}
    json.dump({"meta": meta, "geo": geo}, open(os.path.join(out, "basemap.json"), "w"), separators=(",", ":"))
    print(metro, json.dumps(meta["metro"]))


def build_nation(raw):
    st = gpd.read_file(os.path.join(raw, "cb_2020_us_state_20m")).to_crs(4326)
    st = st[~st.STUSPS.isin(["AK", "HI", "PR"])]
    n = SCALES["nation"]
    out = os.path.join(OUT, "nation"); os.makedirs(out, exist_ok=True)
    land = [ring for g in st.geometry for ring in rings(g, n, 0.02)]
    img, size, lo, hi = terrain(n, raw, land)
    img.save(os.path.join(out, "terrain.png"), optimize=True)
    meta = {"R": R, "elevOffset": 500, "nation": {**n, "size": size, "elevMin": max(lo, -100), "elevMax": hi}}
    geo = {"states": [{"id": r.STATEFP, "abbr": r.STUSPS, "name": r.NAME, "rings": rings(r.geometry, n, 0.02)} for r in st.itertuples()]}
    json.dump({"meta": meta, "geo": geo}, open(os.path.join(out, "basemap.json"), "w"), separators=(",", ":"))
    print("nation", json.dumps(meta["nation"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True, help="cache directory for tiles and cartographic boundary files")
    ap.add_argument("metros", nargs="*", help="metro keys (default: all); 'nation' builds the shared US basemap")
    a = ap.parse_args()
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    from config import METROS
    for k in (a.metros or ["nation", *METROS]):
        build_nation(a.raw) if k == "nation" else build_metro(k, a.raw)


if __name__ == "__main__":
    main()
