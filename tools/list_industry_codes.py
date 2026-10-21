"""List every industry code in a Data Axle bulk business file, with counts.

Reads the whole file (a single CSV/text file, a folder of them, or a zip of
them, without extracting) and writes industry_codes.csv inside a small zip:
one row per detailed code (8-digit NAICS and 6-digit SIC) with its
description, how many businesses have it as their primary code, and how many
have it anywhere (primary or SIC 1-4). Upload that zip to Claude, who picks
the maritime codes from the descriptions.

Needs only Python 3.9+. Run it from PowerShell:
    python list_industry_codes.py "C:\\path\\to\\2024_Business_Academic_QCQ.txt"
"""

from __future__ import annotations

import csv
import io
import sys
import time
import zipfile
from collections import Counter, defaultdict
from collections.abc import Iterator
from pathlib import Path
from typing import IO


def iter_sources(path: Path) -> Iterator[tuple[str, IO[bytes]]]:
    """Yield (file name, binary stream) for each data file under ``path``."""
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


def code_columns(header: list[str]) -> list[tuple[str, int, int | None, bool]]:
    """Find (system, code column, description column, is_primary) for every NAICS/SIC code column."""
    lower = [h.strip().lower() for h in header]
    found = []
    for i, h in enumerate(lower):
        if "desc" in h or "code" not in h:
            continue
        system = "NAICS" if "naics" in h else "SIC" if "sic" in h else None
        if system is None:
            continue
        desc = i + 1 if i + 1 < len(lower) and "desc" in lower[i + 1] else None
        found.append((system, i, desc, h.startswith("primary")))
    return found


def run(source: Path, out_zip: Path) -> None:
    primary: Counter[tuple[str, str]] = Counter()
    anywhere: Counter[tuple[str, str]] = Counter()
    descriptions: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    read = 0
    started = time.time()
    for label, stream in iter_sources(source):
        text = io.TextIOWrapper(stream, encoding="latin-1", newline="")
        first = text.readline()
        delimiter = max((",", "\t", "|"), key=first.count)
        header = next(csv.reader([first], delimiter=delimiter))
        columns = code_columns(header)
        if not columns:
            raise SystemExit("No NAICS or SIC code columns found. Send Claude this header line:\n" + first)
        print(f"{label}: code columns = {[header[c] for _, c, _, _ in columns]}")
        for row in csv.reader(text, delimiter=delimiter):
            read += 1
            if read % 1_000_000 == 0:
                print(f"  ...{read:,} rows read ({time.time() - started:.0f}s)", flush=True)
            seen = set()
            for system, col, desc_col, is_primary in columns:
                if col >= len(row):
                    continue
                code = row[col].strip()
                if not code.isdigit():
                    continue
                key = (system, code)
                if is_primary:
                    primary[key] += 1
                if key not in seen:
                    anywhere[key] += 1
                    seen.add(key)
                if desc_col is not None and desc_col < len(row) and row[desc_col].strip():
                    descriptions[key][row[desc_col].strip()] += 1
    with (
        zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as archive,
        archive.open("industry_codes.csv", "w") as raw,
        io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as out,
    ):
        writer = csv.writer(out)
        writer.writerow(["system", "code", "description", "primary_count", "any_count"])
        for key in sorted(anywhere):
            desc = descriptions[key].most_common(1)[0][0] if descriptions[key] else ""
            writer.writerow([key[0], key[1], desc, primary[key], anywhere[key]])
    print(f"\nDone: read {read:,} businesses; found {len(anywhere):,} distinct codes.")
    print(f"Upload this file to Claude: {out_zip}  ({out_zip.stat().st_size / 1e6:.1f} MB)")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit('Usage: python list_industry_codes.py "C:\\path\\to\\data file.txt"')
    source = Path(sys.argv[1])
    if not source.exists():
        raise SystemExit(f"File not found: {source}")
    out_zip = source.with_name(source.stem + "_codes.zip") if source.is_file() else source / "codes.zip"
    print(f"Reading {source}\nThis can take 20-60 minutes. Leave this window open.\n")
    run(source, out_zip)


if __name__ == "__main__":
    main()
