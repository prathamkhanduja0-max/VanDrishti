"""
scripts/crop_epochs.py
Crops downloaded NEON 1km tiles to each project tile's exact extent and writes
to the exact target filenames expected by epoch discovery.
"""
import glob
import os
import sys
import rasterio
from rasterio.mask import mask
from shapely.geometry import box

RAW = 'data/raw/neon'
DL = os.path.join(RAW, 'download')

ALL_TIFS = glob.glob(os.path.join(DL, '**', '*.tif'), recursive=True)

JOBS = [
    # RGB files
    ('2018_OSBS_4_407000_3284000_image.tif', f'{RAW}/test/OSBS_022_2019.tif', f'{RAW}/test/OSBS_022_2018.tif', None),
    ('2018_OSBS_4_404000_3288000_image.tif', f'{RAW}/test/OSBS_023_2019.tif', f'{RAW}/test/OSBS_023_2018.tif', None),
    ('2019_TEAK_4_321000_4096000_image.tif', f'{RAW}/val/TEAK_043_2018.tif', f'{RAW}/val/TEAK_043_2019.tif', None),
    ('2019_TEAK_4_321000_4097000_image.tif', f'{RAW}/val/TEAK_052_2018.tif', f'{RAW}/val/TEAK_052_2019.tif', None),
    ('2019_SJER_4_256000_4111000_image.tif', f'{RAW}/train/SJER_009_2018.tif', f'{RAW}/train/SJER_009_2019.tif', None),
    ('2019_SJER_4_255000_4112000_image.tif', f'{RAW}/train/SJER_010_2018.tif', f'{RAW}/train/SJER_010_2019.tif', None),
    ('2019_SJER_4_255000_4110000_image.tif', f'{RAW}/train/SJER_021_2018.tif', f'{RAW}/train/SJER_021_2019.tif', None),
    # DTM files
    ('NEON_D17_TEAK_DP3_321000_4096000_DTM.tif', f'{RAW}/val/TEAK_043_2018.tif', f'{RAW}/val/TEAK_043_2019_DTM.tif', '2019'),
    ('NEON_D17_TEAK_DP3_321000_4097000_DTM.tif', f'{RAW}/val/TEAK_052_2018.tif', f'{RAW}/val/TEAK_052_2019_DTM.tif', '2019'),
    ('NEON_D17_SJER_DP3_256000_4111000_DTM.tif', f'{RAW}/train/SJER_009_2018.tif', f'{RAW}/train/SJER_009_2019_DTM.tif', '2019'),
    ('NEON_D17_SJER_DP3_255000_4112000_DTM.tif', f'{RAW}/train/SJER_010_2018.tif', f'{RAW}/train/SJER_010_2019_DTM.tif', '2019'),
    ('NEON_D17_SJER_DP3_255000_4110000_DTM.tif', f'{RAW}/train/SJER_021_2018.tif', f'{RAW}/train/SJER_021_2019_DTM.tif', '2019'),
]


def run_crop():
    for src_name, ref, out, year in JOBS:
        if os.path.exists(out):
            print(f'ERROR: Target already exists: {out}')
            sys.exit(1)

    ok = 0
    for src_name, ref, out, year in JOBS:
        src_candidates = [p for p in ALL_TIFS if os.path.basename(p) == src_name]
        if year:
            src_candidates = [p for p in src_candidates if f'{os.sep}{year}{os.sep}' in p]
        if not src_candidates:
            print(f'ERROR: Source not found for {src_name}')
            sys.exit(1)
        src_path = src_candidates[0]

        with rasterio.open(ref) as r:
            geom = [box(*r.bounds)]

        with rasterio.open(src_path) as s:
            arr, tr = mask(s, geom, crop=True)
            meta = s.meta.copy()
            meta.update(height=arr.shape[1], width=arr.shape[2], transform=tr, count=arr.shape[0])
            with rasterio.open(out, 'w', **meta) as d:
                d.write(arr)

        crs_str = str(meta.get('crs'))
        print(f'OK: {os.path.basename(out):26s} shape={str(arr.shape):15s} bands={arr.shape[0]} crs={crs_str}')
        ok += 1

    print(f'\nTotal {ok} of {len(JOBS)} files written successfully!')


if __name__ == '__main__':
    run_crop()
