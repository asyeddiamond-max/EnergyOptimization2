"""
18_fetch_eaglei_ct.py -- Extract Connecticut rows from ORNL's EAGLE-I dataset,
the research-grade historical cross-validation source for this project's
storm data.

EAGLE-I (Environment for Analysis of Geo-Located Energy Information) is the
DOE/ORNL program that has recorded county-level customers-without-power for
the whole US at 15-minute cadence since 2014, published on figshare:

    "The Environment for Analysis of Geo-Located Energy Information's
     Recorded Electricity Outages 2014-2025"
    doi:10.6084/m9.figshare.24237376 (v4)
    Documented in: Scientific Data 11, 271 (2024),
    doi:10.1038/s41597-024-03095-5

Its collection methodology is scraping utilities' own public outage maps --
the same primary source 17_fetch_live_outages.py reads directly for live
data -- so EAGLE-I serves as the *archived, independent, citable* record of
that same feed. Live mode uses the utility feed (fresher, per-outage
locations); EAGLE-I is the ground truth for after-the-fact validation of
both the historical dataset (data/hartford_doe_oe417.js) and any live-mode
predictions once an event has passed.

The yearly CSVs are ~0.6-1.4 GB each (whole US), so this script STREAMS the
download and keeps only Connecticut rows (~0.3% of the file), writing
data/eaglei_ct_<year>.csv with the original columns:
    fips_code, county, state, sum (customers out), run_start_time (15-min UTC)

Usage:
    python 18_fetch_eaglei_ct.py --year 2020
    python 18_fetch_eaglei_ct.py --year 2020 --year 2021
"""
from __future__ import annotations
import argparse
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
OUT_DIR = HERE / "data"

# figshare file ids for article 24237376 (v4), listed via the public API.
FILE_IDS = {
    2014: 42547717, 2015: 42547822, 2016: 42547825, 2017: 42547828,
    2018: 42547879, 2019: 42547885, 2020: 42547894, 2021: 42547891,
    2022: 42547897, 2023: 44574907, 2024: 53581661, 2025: 62164877,
}
DL = "https://ndownloader.figshare.com/files/{fid}"
UA = {"User-Agent": "Mozilla/5.0 connecticut-grid-resilience/1.0"}


def stream_filter_year(year: int) -> Path:
    fid = FILE_IDS[year]
    out_path = OUT_DIR / f"eaglei_ct_{year}.csv"
    url = DL.format(fid=fid)
    print(f"Streaming {url} (year {year}), filtering to Connecticut rows...")
    req = urllib.request.Request(url, headers=UA)
    t0 = time.time()
    n_total = 0
    n_ct = 0
    header = None
    buf = b""
    with urllib.request.urlopen(req, timeout=120) as r, open(out_path, "w", encoding="utf-8", newline="") as out:
        while True:
            chunk = r.read(1 << 20)  # 1 MB
            if not chunk:
                break
            buf += chunk
            lines = buf.split(b"\n")
            buf = lines.pop()  # trailing partial line
            for raw in lines:
                line = raw.decode("utf-8", errors="replace").rstrip("\r")
                if header is None:
                    header = line
                    out.write(header + "\n")
                    continue
                n_total += 1
                # state is the 3rd column; substring check is a fast pre-filter,
                # exact column check below protects against e.g. a county name
                # ever containing the string.
                if "Connecticut" not in line:
                    continue
                parts = line.split(",")
                if len(parts) >= 3 and parts[2] == "Connecticut":
                    out.write(line + "\n")
                    n_ct += 1
            if n_total and n_total % 5_000_000 < 40000:
                mb = (time.time() - t0)
                print(f"  ... {n_total/1e6:.0f}M rows scanned, {n_ct} CT rows, {mb:.0f}s elapsed")
        if buf:
            line = buf.decode("utf-8", errors="replace").rstrip("\r")
            parts = line.split(",")
            if len(parts) >= 3 and parts[2] == "Connecticut":
                out.write(line + "\n")
                n_ct += 1
    print(f"  done: {n_total:,} rows scanned -> {n_ct:,} CT rows in {time.time()-t0:.0f}s")
    print(f"  wrote {out_path}")
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, action="append", required=True,
                    choices=sorted(FILE_IDS), help="Year(s) to extract")
    args = ap.parse_args()
    for y in args.year:
        stream_filter_year(y)


if __name__ == "__main__":
    main()
