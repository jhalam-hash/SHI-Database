"""Cut a Data Axle bulk business file down to SHI maritime companies.

The U-M Library's yearly Data Axle file is one CSV per state inside a ~60 GB
zip. This script reads that zip (or a folder of the CSVs) directly, without
extracting it, keeps only businesses with an SHI NAICS code, and writes them to
a small zip you can upload.

A business is kept when any of its NAICS columns starts with a code below and:
  * the code is "core" (every business under it is maritime), or
  * the code is "broad" and the company name contains one of its keywords, or
    a marine term (marine, ship..., boat..., naval, harbor, ...) when the code
    has no keywords of its own, or
  * the code is one of the small specialized codes in INCLUDE_ALL_CODES; such rows
    are marked "SHI Needs Verification" = yes.

Needs only Python 3.9+ (python.org or the Microsoft Store); no extra packages.
Run it by double-clicking it and choosing the zip, or from a terminal:
    python filter_maritime_bulk.py "C:\\path\\to\\990166537600106381.2024.001.zip"

Keep this list in step with data/marine_naics_codes.csv (tests check it).
"""

from __future__ import annotations

import csv
import io
import re
import sys
import time
import zipfile
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import IO

# (NAICS code, SHI category, tier, own keywords)
TARGETS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("336611", "Shipyards", "core", ()),
    ("336612", "Shipyards", "core", ()),
    ("488310", "Maritime Contractors", "core", ()),
    ("488330", "Maritime Contractors", "core", ()),
    ("488390", "Maritime Contractors", "core", ()),
    ("237990", "Maritime Contractors", "broad", ()),
    ("811310", "Maritime Contractors", "broad", ()),
    ("333618", "Maritime Contractors", "broad", ()),
    ("334511", "Maritime Contractors", "broad", ()),
    ("541330", "Independent Design Firms", "broad", ()),
    ("541410", "Independent Design Firms", "broad", ("yacht", "marine", "boat", "vessel", "ship")),
    ("928110", "Government Design Organizations", "broad", ()),
    ("926120", "Government Design Organizations", "broad", ()),
    ("541715", "Hydrodynamics Specialists", "broad", ()),
    ("541380", "Hydrodynamics Specialists", "broad", ()),
    ("541690", "Hydrodynamics Specialists", "broad", ()),
    (
        "541330",
        "Hydrodynamics Specialists",
        "broad",
        ("hydrodynamic", "hydro", "towing tank", "model basin", "ocean engineering", "CFD", "propeller"),
    ),
    ("541370", "Marine Engineering Organizations", "broad", ()),
    ("541990", "Marine Engineering Organizations", "broad", ()),
    ("813920", "Marine Engineering Organizations", "broad", ()),
    ("813910", "Marine Engineering Organizations", "broad", ()),
    ("221115", "Offshore Wind", "broad", ("offshore wind", "floating wind", "offshore", "subsea")),
    ("237130", "Offshore Wind", "broad", ("offshore wind", "floating wind", "offshore", "subsea")),
    ("333611", "Offshore Wind", "broad", ("offshore wind", "floating wind", "offshore", "subsea")),
    ("335929", "Offshore Wind", "broad", ("offshore wind", "floating wind", "offshore", "subsea")),
    ("331420", "Offshore Wind", "broad", ("subsea", "submarine cable", "offshore")),
    ("211120", "Offshore Oil & Gas", "broad", ("offshore", "subsea", "deepwater")),
    ("213111", "Offshore Oil & Gas", "broad", ("offshore", "subsea", "marine", "deepwater")),
    ("213112", "Offshore Oil & Gas", "broad", ("offshore", "subsea", "marine", "deepwater")),
    ("541360", "Offshore Oil & Gas", "broad", ("offshore", "marine", "subsea", "ocean")),
    ("211130", "Offshore Oil & Gas", "broad", ("offshore", "subsea", "deepwater")),
    ("483111", "Water Transportation", "core", ()),
    ("483112", "Water Transportation", "core", ()),
    ("483113", "Water Transportation", "core", ()),
    ("483114", "Water Transportation", "core", ()),
    ("483211", "Water Transportation", "core", ()),
    ("483212", "Water Transportation", "core", ()),
    ("488320", "Ports & Cargo", "core", ()),
    ("488510", "Ports & Cargo", "broad", ("ocean", "maritime", "marine", "shipping", "vessel", "port")),
    ("713930", "Recreational Marine", "core", ()),
    ("441222", "Recreational Marine", "core", ()),
    ("487210", "Recreational Marine", "core", ()),
    ("811490", "Recreational Marine", "broad", ("boat", "marine", "yacht", "outboard")),
    ("423860", "Marine Suppliers", "broad", ()),
    ("532411", "Marine Suppliers", "broad", ("vessel", "marine", "boat", "barge", "ship", "tug")),
    ("423910", "Marine Suppliers", "broad", ("marine", "boat", "yacht", "outboard")),
    ("114111", "Fishing & Maritime Education", "core", ()),
    ("114112", "Fishing & Maritime Education", "core", ()),
    (
        "611310",
        "Fishing & Maritime Education",
        "broad",
        ("maritime", "merchant marine", "naval", "ocean engineering"),
    ),
)

MARINE_NAME = re.compile(
    r"\b(marine|maritime|naval|navy|navsea|ship\w*|boat\w*|yacht\w*|vessel\w*|hull|"
    r"offshore|subsea|ocean\w*|hydro\w*|harbou?r|port|dock\w*|dredg\w*|propeller\w*|"
    r"sonar|coast guard|carderock|seakeeping|tug\w*|barge\w*|nautic\w*)\b",
    re.IGNORECASE,
)
CODES = {code for code, *_ in TARGETS}
CODE_IN_LINE = re.compile("|".join(sorted(CODES)).encode())
NAME_HEADERS = ("company name", "company", "business name", "conm", "coname", "name")


def keyword_pattern(keywords: tuple[str, ...]) -> re.Pattern[str]:
    """Match any keyword at the start of a word ("port" matches Portland, not transport)."""
    return re.compile(r"\b(" + "|".join(re.escape(k) for k in keywords) + ")", re.IGNORECASE)


RULES = [(code, cat, tier, keyword_pattern(kws) if kws else None) for code, cat, tier, kws in TARGETS]

# Small, specialized broad codes kept in full even without a marine word in the name.
# Those rows are marked "SHI Needs Verification" = yes so they can be checked one by one.
INCLUDE_ALL_CODES = frozenset(
    {"333618", "333611", "335929", "331420", "213111", "211130", "221115", "532411"}
)


def match(codes: list[str], name: str) -> list[tuple[str, str]]:
    """Return the (code, category) pairs this business qualifies for."""
    hits = []
    for code, category, tier, pattern in RULES:
        if code not in codes:
            continue
        if tier == "core" or (pattern.search(name) if pattern else MARINE_NAME.search(name)):
            hits.append((code, category))
    return hits


def unverified_matches(codes: list[str], name: str) -> list[tuple[str, str]]:
    """(code, category) pairs kept only because the code is in INCLUDE_ALL_CODES."""
    confirmed = set(match(codes, name))
    return [
        (code, category)
        for code, category, _, _ in RULES
        if code in codes and code in INCLUDE_ALL_CODES and (code, category) not in confirmed
    ]


def find_columns(header: list[str]) -> tuple[list[int], int]:
    """Locate the NAICS code columns and the company-name column."""
    lower = [h.strip().lower() for h in header]
    naics = [i for i, h in enumerate(lower) if "naics" in h and "desc" not in h and "title" not in h]
    name = next((lower.index(h) for h in NAME_HEADERS if h in lower), -1)
    if name < 0:
        name = next((i for i, h in enumerate(lower) if "company" in h or "business name" in h), -1)
    if not naics or name < 0:
        raise SystemExit(
            "Could not find the NAICS and company-name columns. Please send Claude this header line:\n"
            + ",".join(header)
        )
    return naics, name


def iter_csv_sources(path: Path) -> Iterator[tuple[str, IO[bytes]]]:
    """Yield (file name, binary stream) for each data file: a single CSV/text file, every
    CSV/text file in a folder, or every one inside a zip (read without extracting)."""
    if path.is_dir():
        for data_path in sorted(p for p in path.rglob("*") if p.suffix.lower() in (".csv", ".txt")):
            with data_path.open("rb") as stream:
                yield data_path.name, stream
        return
    if not zipfile.is_zipfile(path):
        with path.open("rb") as stream:
            yield path.name, stream
        return
    with zipfile.ZipFile(path) as archive:
        for info in sorted(archive.infolist(), key=lambda i: i.filename):
            if info.filename.lower().endswith((".csv", ".txt")):
                with archive.open(info) as stream:
                    yield Path(info.filename).name, stream


def run(source: Path, out_zip: Path) -> None:
    """Filter every data file under ``source`` into ``out_zip``."""
    kept, read, bad, unverified = 0, 0, 0, 0
    per_category: Counter[str] = Counter()
    header_out: list[str] | None = None
    started = time.time()
    with (
        zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as out_archive,
        out_archive.open("maritime_companies.csv", "w") as raw_out,
        io.TextIOWrapper(raw_out, encoding="utf-8-sig", newline="") as out,
    ):
        writer = csv.writer(out)
        for label, stream in iter_csv_sources(source):
            lines = iter(stream)
            first = next(lines).decode("latin-1")
            delimiter = max((",", "\t", "|"), key=first.count)
            header = next(csv.reader([first], delimiter=delimiter))
            naics_cols, name_col = find_columns(header)
            if header_out is None:
                extra_cols = ["SHI Categories", "SHI Matched NAICS", "SHI Needs Verification", "Source File"]
                header_out = [*header, *extra_cols]
                writer.writerow(header_out)
                naics_names = [header[i] for i in naics_cols]
                print(f"Columns found: name = {header[name_col]!r}; NAICS = {naics_names}")
            file_kept = 0
            for raw in lines:
                read += 1
                if read % 1_000_000 == 0:
                    elapsed = time.time() - started
                    print(f"  ...{read:,} rows read, {kept:,} kept so far ({elapsed:.0f}s)", flush=True)
                if not CODE_IN_LINE.search(raw):
                    continue
                try:
                    row = next(csv.reader([raw.decode("latin-1")], delimiter=delimiter))
                    row_codes = [row[i].strip()[:6] for i in naics_cols if i < len(row)]
                    hits = match(row_codes, row[name_col])
                    extra = unverified_matches(row_codes, row[name_col])
                except (StopIteration, IndexError, csv.Error):
                    bad += 1
                    continue
                if not hits and not extra:
                    continue
                categories = sorted({category for _, category in hits + extra})
                codes = sorted({code for code, _ in hits + extra})
                per_category.update(categories)
                needs_check = "" if hits else "yes"
                unverified += bool(needs_check)
                writer.writerow([*row, "; ".join(categories), "; ".join(codes), needs_check, label])
                kept += 1
                file_kept += 1
            elapsed = time.time() - started
            print(f"  {label}: kept {file_kept:,}  (total {kept:,} of {read:,} read, {elapsed:.0f}s)")
    print(f"\nDone: kept {kept:,} maritime businesses out of {read:,}; {bad:,} unreadable lines skipped.")
    print(f"{unverified:,} of them are kept only by NAICS code and need checking (SHI Needs Verification).")
    for category, n in per_category.most_common():
        print(f"  {category}: {n:,}")
    print(f"\nUpload this file to Claude: {out_zip}  ({out_zip.stat().st_size / 1e6:.1f} MB)")


def main() -> None:
    if len(sys.argv) > 1:
        source = Path(sys.argv[1])
    else:
        try:
            from tkinter import Tk, filedialog

            Tk().withdraw()
            source = Path(filedialog.askopenfilename(title="Choose the Data Axle zip file") or "")
        except Exception:
            source = Path(input("Path to the Data Axle zip file (or folder): ").strip().strip('"'))
    if not source.exists() or str(source) in ("", "."):
        raise SystemExit("No file chosen.")
    out_zip = source.with_name(source.stem + "_maritime.zip") if source.is_file() else source / "maritime.zip"
    print(f"Reading {source}\nThis can take 30-90 minutes for the full U.S. file. Leave this window open.\n")
    run(source, out_zip)


if __name__ == "__main__":
    try:
        main()
    finally:
        if len(sys.argv) <= 1:
            input("\nPress Enter to close this window.")
