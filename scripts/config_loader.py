"""
config_loader.py  -- VanDrishti

Two jobs:

  1. Load a site config so the pipeline is not welded to OSBS.
  2. Inspect what data a site actually HAS, and report honestly which modules
     can run at full capability, which run degraded, and which cannot run.

The second job matters more than it looks. Three of the five modules depend on
LiDAR products (DTM, CHM) that most users will not have. A system that silently
falls back and prints numbers anyway is worse than one that says "I cannot
compute this". This module makes the pipeline state its own limits.

CAPABILITY LEVELS
  FULL      all required inputs present
  DEGRADED  runs, but on a weaker substitute (e.g. ExG instead of CHM)
  BLOCKED   required input missing, module will not run

Usage:
    python scripts/config_loader.py --config config.yaml
    python scripts/config_loader.py --config config_myforest.yaml --json
"""

import argparse
import json
import os
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

# module -> (required inputs, optional inputs that upgrade capability)
MODULE_REQUIREMENTS = {
    "detection": {
        "required": ["rgb_t2"],
        "upgrades": {"chm_t2": "LiDAR height validation of detections"},
        "note": "needs a georeferenced RGB raster",
    },
    "priority": {
        "required": ["rgb_t2"],
        "upgrades": {"chm_t2": "height-based priority instead of confidence proxy"},
        "note": "corridor geometry must be supplied in config",
    },
    "routing": {
        "required": ["rgb_t2"],
        "upgrades": {
            "chm_t2": "canopy-height impedance instead of ExG greenness",
            "dtm": "Tobler slope cost (true terrain-awareness)",
        },
        "note": "runs on ExG alone, but that is a weak impedance proxy",
    },
    "degradation": {
        "required": ["chm_t1", "chm_t2"],
        "upgrades": {"rgb_t1": "spectral cross-check alongside height change"},
        "note": "height differencing needs two LiDAR CHM acquisitions",
    },
    "health_score": {
        "required": ["chm_t1", "chm_t2"],
        "upgrades": {},
        "note": "cover, structural diversity and degradation all derive from CHM",
    },
    "fire": {
        "required": [],
        "upgrades": {},
        "note": "NASA FIRMS is a live API; 375 m pixels are regional context only",
    },
}

RASTER_KEYS = ["rgb_t1", "rgb_t2", "chm_t1", "chm_t2", "dtm", "dsm"]


class Config(dict):
    """Dict with attribute access and path resolution."""

    def __getattr__(self, k):
        try:
            v = self[k]
        except KeyError:
            raise AttributeError(k)
        return Config(v) if isinstance(v, dict) else v

    def path(self, *keys, required=False):
        """Resolve a possibly-relative path from the config against REPO_ROOT."""
        node = self
        for k in keys:
            if not isinstance(node, dict) or k not in node:
                if required:
                    raise KeyError(f"config missing: {'.'.join(keys)}")
                return None
            node = node[k]
        if node in (None, "", "null"):
            return None
        p = Path(node)
        return p if p.is_absolute() else (REPO_ROOT / p)


def load(config_path):
    with open(config_path) as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ValueError(f"{config_path} did not parse to a mapping")
    return Config(raw)


# --------------------------------------------------------------------------
def inspect_rasters(cfg):
    """Which declared rasters exist, and what are their basic properties."""
    import rasterio

    found = {}
    for key in RASTER_KEYS:
        p = cfg.path("site", "rasters", key)
        if p is None:
            found[key] = {"declared": False, "exists": False}
            continue
        if not p.exists():
            found[key] = {"declared": True, "exists": False, "path": str(p)}
            continue
        try:
            with rasterio.open(p) as s:
                found[key] = {
                    "declared": True,
                    "exists": True,
                    "path": str(p),
                    "shape": [s.height, s.width],
                    "res_m": round(abs(s.transform.a), 3),
                    "crs": str(s.crs) if s.crs else None,
                    "georeferenced": s.crs is not None,
                    "projected": bool(s.crs and s.crs.is_projected),
                    "bands": s.count,
                }
        except Exception as e:
            found[key] = {"declared": True, "exists": True, "path": str(p),
                          "error": str(e)}
    return found


def assess(rasters):
    """Capability per module, given what actually exists on disk."""
    def have(k):
        r = rasters.get(k, {})
        return bool(r.get("exists") and not r.get("error"))

    report = {}
    for mod, spec in MODULE_REQUIREMENTS.items():
        missing = [k for k in spec["required"] if not have(k)]
        if missing:
            report[mod] = {
                "level": "BLOCKED",
                "missing": missing,
                "note": spec["note"],
                "lost_capability": [],
            }
            continue

        lost = [f"{k}: {why}" for k, why in spec["upgrades"].items() if not have(k)]
        report[mod] = {
            "level": "FULL" if not lost else "DEGRADED",
            "missing": [],
            "note": spec["note"],
            "lost_capability": lost,
        }
    return report


def crs_warnings(rasters):
    """Problems that will silently corrupt results if not caught early."""
    warns = []
    present = {k: v for k, v in rasters.items()
               if v.get("exists") and not v.get("error")}

    for k, v in present.items():
        if not v.get("georeferenced"):
            warns.append(
                f"{k} has no CRS. Areas, distances and UTM coordinates will be "
                "meaningless. Georeference before use.")
        elif not v.get("projected"):
            warns.append(
                f"{k} is in a geographic CRS ({v['crs']}). Metric operations "
                "(crown size, route length, cell area) require a projected CRS.")

    crss = {v["crs"] for v in present.values() if v.get("crs")}
    if len(crss) > 1:
        warns.append(f"rasters span multiple CRS: {sorted(crss)}. "
                     "Reproject to a common projected CRS first.")

    # paired rasters must share a grid
    for a, b, label in [("chm_t1", "chm_t2", "CHM pair"),
                        ("rgb_t1", "rgb_t2", "RGB pair")]:
        ra, rb = present.get(a), present.get(b)
        if ra and rb and ra.get("shape") != rb.get("shape"):
            warns.append(
                f"{label} shapes differ ({ra['shape']} vs {rb['shape']}). "
                "Change detection requires identical grids -- clip both first.")

    return warns


def summarise(cfg, rasters, caps, warns):
    site = cfg.get("site", {}).get("name", "unnamed")
    full = sum(1 for c in caps.values() if c["level"] == "FULL")
    deg = sum(1 for c in caps.values() if c["level"] == "DEGRADED")
    blocked = sum(1 for c in caps.values() if c["level"] == "BLOCKED")

    print(f"\n=== VanDrishti capability report: {site} ===\n")

    print("Data present:")
    for k in RASTER_KEYS:
        r = rasters[k]
        if not r.get("declared"):
            print(f"  {k:<8} -- not declared in config")
        elif not r.get("exists"):
            print(f"  {k:<8} MISSING  {r.get('path','')}")
        elif r.get("error"):
            print(f"  {k:<8} UNREADABLE  {r['error']}")
        else:
            print(f"  {k:<8} ok  {r['shape'][0]}x{r['shape'][1]} @ "
                  f"{r['res_m']} m  {r['crs']}")

    print("\nModules:")
    icon = {"FULL": "[FULL]    ", "DEGRADED": "[DEGRADED]", "BLOCKED": "[BLOCKED] "}
    for mod, c in caps.items():
        print(f"  {icon[c['level']]} {mod}")
        if c["level"] == "BLOCKED":
            print(f"      needs: {', '.join(c['missing'])}  ({c['note']})")
        for l in c["lost_capability"]:
            print(f"      without {l}")

    if warns:
        print("\nWarnings:")
        for w in warns:
            print(f"  ! {w}")

    print(f"\nSummary: {full} full, {deg} degraded, {blocked} blocked "
          f"of {len(caps)} modules")
    if blocked:
        print("Blocked modules will not produce output. Do not report numbers")
        print("for them, and state the data gap in any writeup.\n")
    else:
        print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(REPO_ROOT / "config.yaml"))
    ap.add_argument("--json", action="store_true",
                    help="emit machine-readable report instead of text")
    args = ap.parse_args()

    cfg = load(args.config)
    rasters = inspect_rasters(cfg)
    caps = assess(rasters)
    warns = crs_warnings(rasters)

    if args.json:
        print(json.dumps({
            "site": cfg.get("site", {}).get("name"),
            "rasters": rasters,
            "capabilities": caps,
            "warnings": warns,
        }, indent=2))
    else:
        summarise(cfg, rasters, caps, warns)


if __name__ == "__main__":
    main()
