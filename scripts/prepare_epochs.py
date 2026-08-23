"""Crops downloaded NEON 1km tiles to each project tile's extent and renames
them to the convention that epoch discovery expects."""
import glob, os
import rasterio
from rasterio.mask import mask
from shapely.geometry import box

RAW = 'data/raw/neon'
DL = os.path.join(RAW, 'download')

# (reference file, easting, northing, output path, kind)
JOBS = [
    # --- second-epoch CHM: unblocks degradation + health_score ---
    (f'{RAW}/test/OSBS_022_2019.tif',  407000, 3284000, f'{RAW}/test/OSBS_022_2018_CHM.tif',  'CHM'),
    (f'{RAW}/test/OSBS_023_2019.tif',  404000, 3288000, f'{RAW}/test/OSBS_023_2018_CHM.tif',  'CHM'),
    (f'{RAW}/val/TEAK_043_2018.tif',   321000, 4096000, f'{RAW}/val/TEAK_043_2019_CHM.tif',   'CHM'),
    (f'{RAW}/val/TEAK_052_2018.tif',   321000, 4097000, f'{RAW}/val/TEAK_052_2019_CHM.tif',   'CHM'),
    (f'{RAW}/train/SJER_009_2018.tif', 256000, 4111000, f'{RAW}/train/SJER_009_2019_CHM.tif', 'CHM'),
    (f'{RAW}/train/SJER_010_2018.tif', 255000, 4112000, f'{RAW}/train/SJER_010_2019_CHM.tif', 'CHM'),
    (f'{RAW}/train/SJER_021_2018.tif', 255000, 4110000, f'{RAW}/train/SJER_021_2019_CHM.tif', 'CHM'),
    # --- same-epoch DTM: upgrades routing to full Tobler slope ---
    (f'{RAW}/test/OSBS_022_2019.tif',  407000, 3284000, f'{RAW}/test/OSBS_022_2019_DTM.tif',  'DTM'),
    (f'{RAW}/test/OSBS_023_2019.tif',  404000, 3288000, f'{RAW}/test/OSBS_023_2019_DTM.tif',  'DTM'),
    (f'{RAW}/val/TEAK_052_2018.tif',   321000, 4097000, f'{RAW}/val/TEAK_052_2018_DTM.tif',   'DTM'),
    (f'{RAW}/train/SJER_009_2018.tif', 256000, 4111000, f'{RAW}/train/SJER_009_2018_DTM.tif', 'DTM'),
    (f'{RAW}/train/SJER_010_2018.tif', 255000, 4112000, f'{RAW}/train/SJER_010_2018_DTM.tif', 'DTM'),
    (f'{RAW}/train/SJER_021_2018.tif', 255000, 4110000, f'{RAW}/train/SJER_021_2018_DTM.tif', 'DTM'),
]

ALL_TIFS = glob.glob(os.path.join(DL, '**', '*.tif'), recursive=True)
print(f'Found {len(ALL_TIFS)} downloaded tiles in {DL}\n')


def find_tile(easting, northing, kind, year):
    """Match by UTM tile origin, product kind, and acquisition year."""
    hits = []
    for p in ALL_TIFS:
        name = os.path.basename(p)
        if f'_{easting}_{northing}_' not in name:
            continue
        if not name.endswith(f'_{kind}.tif'):
            continue
        if f'{os.sep}{year}{os.sep}' not in p:
            continue
        hits.append(p)
    return hits[0] if hits else None


ok = skipped = 0
for ref, e, n, out, kind in JOBS:
    year = os.path.basename(out).split('_')[2]

    if not os.path.exists(ref):
        print(f'SKIP  {os.path.basename(out):26} reference missing')
        skipped += 1
        continue

    src_path = find_tile(e, n, kind, year)
    if not src_path:
        print(f'SKIP  {os.path.basename(out):26} no {year} {kind} tile at {e},{n}')
        skipped += 1
        continue

    with rasterio.open(ref) as r:
        geom = [box(*r.bounds)]
    with rasterio.open(src_path) as s:
        arr, tr = mask(s, geom, crop=True)
        meta = s.meta.copy()
        meta.update(height=arr.shape[1], width=arr.shape[2], transform=tr)
        with rasterio.open(out, 'w', **meta) as d:
            d.write(arr)

    print(f'OK    {os.path.basename(out):26} {arr.shape[2]}x{arr.shape[1]} px')
    ok += 1

print(f'\nDone: {ok} written, {skipped} skipped')