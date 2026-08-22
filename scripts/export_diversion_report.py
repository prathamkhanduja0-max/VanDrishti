"""
export_diversion_report.py -- VanDrishti
CLI utility to generate CSV inventory and PDF reports for Site-Specific Forest Diversion Assessments.

Usage:
  python scripts/export_diversion_report.py --site OSBS_large_2019 --out-dir results/gis
"""

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.services.report_generator import generate_diversion_csv, generate_diversion_pdf


def main():
    parser = argparse.ArgumentParser(description="Export VanDrishti Forest Diversion Assessment Reports")
    parser.add_argument("--site", default="OSBS_large_2019", help="Site identifier (OSBS_large_2019 or TEAK_043_2018)")
    parser.add_argument("--out-dir", default=None, help="Output directory for generated reports")
    args = parser.parse_args()

    site_name = args.site
    out_dir = Path(args.out_dir) if args.out_dir else (REPO_ROOT / "results" / "gis")
    out_dir.mkdir(parents=True, exist_ok=True)

    csv_path = out_dir / f"van_drishti_diversion_inventory_{site_name}.csv"
    pdf_path = out_dir / f"van_drishti_diversion_report_{site_name}.pdf"

    print(f"=== Generating Forest Diversion Assessment Reports for site '{site_name}' ===")

    # 1. Export CSV
    csv_content = generate_diversion_csv(site_name)
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write(csv_content)
    print(f"[+] CSV Inventory Export saved: {csv_path}")

    # 2. Export PDF
    pdf_bytes = generate_diversion_pdf(site_name)
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)
    print(f"[+] PDF Assessment Report saved: {pdf_path}")

    print("=== Export Complete ===")


if __name__ == "__main__":
    main()
