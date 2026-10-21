"""Cut a Data Axle bulk business file down to SHI maritime companies, by industry code.

The U-M Library's yearly Data Axle file is one very large text/CSV file (or a zip of
state files). This script reads it directly, without extracting, keeps only
businesses with a maritime industry code, and writes them to a small zip you can
upload. A business is kept when:
  * its primary NAICS code is one of the core maritime codes below, or
  * any of its SIC codes (primary or SIC 1-4) is one of the maritime SIC codes below.
Wind-energy and college codes are kept only when the company name contains one of
their words (offshore wind farms; maritime/naval academies). No other name keywords.

Needs only Python 3.9+. Run it from PowerShell:
    python filter_maritime_bulk.py "C:\\path\\to\\2024_Business_Academic_QCQ.txt"

The code lists mirror data/marine_naics_codes.csv (core codes) and
data/maritime_sic_codes.csv; tests check they stay in step.
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

WIND_WORDS = ("offshore", "floating", "subsea", "marine", "ocean", "sea", "coastal")
COLLEGE_WORDS = ("maritime", "merchant marine", "naval", "marine", "ocean", "nautical", "coast guard")

# (system, code, SHI category, name keywords: empty = keep every business with the code)
CODES: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("NAICS", "336611", "Shipyards", ()),  # Ship Building and Repairing
    ("NAICS", "336612", "Shipyards", ()),  # Boat Building
    ("NAICS", "488310", "Maritime Contractors", ()),  # Port and Harbor Operations
    ("NAICS", "488330", "Maritime Contractors", ()),  # Navigational Services to Shipping
    ("NAICS", "488390", "Maritime Contractors", ()),  # Other Support Activities for Water Transportation
    ("NAICS", "483111", "Water Transportation", ()),  # Deep Sea Freight Transportation
    ("NAICS", "483112", "Water Transportation", ()),  # Deep Sea Passenger Transportation
    ("NAICS", "483113", "Water Transportation", ()),  # Coastal and Great Lakes Freight Transportation
    ("NAICS", "483114", "Water Transportation", ()),  # Coastal and Great Lakes Passenger Transportation
    ("NAICS", "483211", "Water Transportation", ()),  # Inland Water Freight Transportation
    ("NAICS", "483212", "Water Transportation", ()),  # Inland Water Passenger Transportation
    ("NAICS", "488320", "Ports & Cargo", ()),  # Marine Cargo Handling
    ("NAICS", "713930", "Recreational Marine", ()),  # Marinas
    ("NAICS", "441222", "Recreational Marine", ()),  # Boat Dealers
    ("NAICS", "487210", "Recreational Marine", ()),  # Scenic and Sightseeing Transportation, Water
    ("NAICS", "114111", "Fishing & Maritime Education", ()),  # Finfish Fishing
    ("NAICS", "114112", "Fishing & Maritime Education", ()),  # Shellfish Fishing
    ("NAICS", "221115", "Offshore Wind", WIND_WORDS),  # Wind Electric Power Generation
    ("NAICS", "611310", "Fishing & Maritime Education", COLLEGE_WORDS),  # Colleges and Universities
    ("SIC", "373101", "Shipyards", ()),  # SHIP BUILDERS & REPAIRERS (MFRS)
    ("SIC", "373102", "Shipyards", ()),  # BARGES (MFRS)
    ("SIC", "373104", "Shipyards", ()),  # SHIP YARDS (MFRS)
    ("SIC", "373201", "Shipyards", ()),  # BOATS-MANUFACTURERS
    ("SIC", "373203", "Shipyards", ()),  # CANOE-MANUFACTURERS
    ("SIC", "373206", "Shipyards", ()),  # YACHTS-MANUFACTURERS
    ("SIC", "373207", "Shipyards", ()),  # YACHTS-REPAIRING (MFRS)
    ("SIC", "162902", "Maritime Contractors", ()),  # DOCKS (BUILDERS)
    ("SIC", "162903", "Maritime Contractors", ()),  # MARINE CONTRACTORS & DESIGNERS
    ("SIC", "162914", "Maritime Contractors", ()),  # DREDGING
    ("SIC", "162917", "Maritime Contractors", ()),  # SEA WALL CONTRACTORS
    ("SIC", "162939", "Maritime Contractors", ()),  # RIVERS & CANALS
    ("SIC", "172114", "Maritime Contractors", ()),  # SHIP PAINTING
    ("SIC", "173105", "Maritime Contractors", ()),  # ELECTRIC CONTRACTORS-MARINE
    ("SIC", "221114", "Maritime Contractors", ()),  # SAILS-REPAIR & RECONDITION (MFRS)
    ("SIC", "239401", "Maritime Contractors", ()),  # SAILMAKERS (MFRS)
    ("SIC", "239404", "Maritime Contractors", ()),  # BOAT COVERS TOPS & UPHOLSTERY-MFRS
    ("SIC", "306922", "Maritime Contractors", ()),  # LIFE PRESERVERS-MANUFACTURERS
    ("SIC", "306923", "Maritime Contractors", ()),  # LIFE RAFTS & FLOATS-MANUFACTURERS
    ("SIC", "306930", "Maritime Contractors", ()),  # PONTOONS (MFRS)
    ("SIC", "308917", "Maritime Contractors", ()),  # BUOYS-MARINE (MFRS)
    ("SIC", "336607", "Maritime Contractors", ()),  # PROPELLERS-MFRS
    ("SIC", "342908", "Maritime Contractors", ()),  # HARDWARE-MARINE-MANUFACTURERS
    ("SIC", "344806", "Maritime Contractors", ()),  # DOCKS-MANUFACTURERS
    ("SIC", "353121", "Maritime Contractors", ()),  # SHIP BUILDING EQUIP & SUPPLIES (MFRS)
    ("SIC", "353124", "Maritime Contractors", ()),  # DREDGING MACHINERY-MFRS
    ("SIC", "353602", "Maritime Contractors", ()),  # BOAT LIFTS (MFRS)
    ("SIC", "358512", "Maritime Contractors", ()),  # MARINE REFRIGERATION & AIR COND-MFRS
    ("SIC", "366303", "Maritime Contractors", ()),  # MARINE ELECTRONICS MFRS
    ("SIC", "369405", "Maritime Contractors", ()),  # ALTERNATORS & STARTERS-MARINE (MFRS)
    ("SIC", "373202", "Maritime Contractors", ()),  # BOAT EQUIPMENT & SUPPLIES-MANUFACTURERS
    ("SIC", "373204", "Maritime Contractors", ()),  # MARINE EQUIPMENT & SUPPLIES-MFRS
    ("SIC", "373298", "Maritime Contractors", ()),  # BOAT PART-USED & REBUILT (MFRS)
    ("SIC", "381204", "Maritime Contractors", ()),  # MARINE INSTRUMENTS-MANUFACTURERS
    ("SIC", "394932", "Maritime Contractors", ()),  # JET DRIVES-MARINE (MFRS)
    ("SIC", "399938", "Maritime Contractors", ()),  # YACHT FURNISHINGS-MANUFACTURERS
    ("SIC", "449102", "Maritime Contractors", ()),  # DOCKS (FACILITY)
    ("SIC", "449104", "Maritime Contractors", ()),  # PORTS
    ("SIC", "449105", "Maritime Contractors", ()),  # SHIP CLEANING
    ("SIC", "449107", "Maritime Contractors", ()),  # SHIP MOORING LINE SERVICE
    ("SIC", "449201", "Maritime Contractors", ()),  # TOW BOAT SERVICE
    ("SIC", "449202", "Maritime Contractors", ()),  # TOWING-MARINE
    ("SIC", "449305", "Maritime Contractors", ()),  # MARINE REPAIRS
    ("SIC", "449308", "Maritime Contractors", ()),  # DRY DOCKS
    ("SIC", "449310", "Maritime Contractors", ()),  # VESSEL DOCUMENTATION
    ("SIC", "449902", "Maritime Contractors", ()),  # SALVAGE-MARINE
    ("SIC", "449906", "Maritime Contractors", ()),  # PILOTS-MARINE
    ("SIC", "449908", "Maritime Contractors", ()),  # MARINE WAYS
    ("SIC", "449912", "Maritime Contractors", ()),  # SHIP WRECKERS
    ("SIC", "449913", "Maritime Contractors", ()),  # MARINE DOCUMENTATION
    ("SIC", "449999", "Maritime Contractors", ()),  # WATER TRANSPORTATION SERVICES NEC
    ("SIC", "738941", "Maritime Contractors", ()),  # DIVERS
    ("SIC", "762917", "Maritime Contractors", ()),  # MARINE ELECTRIC SERVICE
    ("SIC", "762944", "Maritime Contractors", ()),  # MARINE ELECTRONIC EQUIP-REPAIRING & SVC
    ("SIC", "769975", "Maritime Contractors", ()),  # ENGINES-MARINE-REPAIRING
    ("SIC", "769994", "Maritime Contractors", ()),  # PROPELLERS-REPAIRING
    ("SIC", "871101", "Independent Design Firms", ()),  # NAVAL ARCHITECTS
    ("SIC", "871126", "Independent Design Firms", ()),  # ENGINEERS-MARINE
    ("SIC", "871187", "Independent Design Firms", ()),  # ENGINEERS NAVAL
    ("SIC", "873107", "Hydrodynamics Specialists", ()),  # OCEANOGRAPHERS
    ("SIC", "873123", "Hydrodynamics Specialists", ()),  # LABORATORIES-MARINE BIOLOGICAL
    ("SIC", "873314", "Hydrodynamics Specialists", ()),  # OCEANOGRAPHIC RESEARCH & DEVELOPMENT
    ("SIC", "448904", "Marine Engineering Organizations", ()),  # MARINE TRANSPORTATION CONSULTANTS
    ("SIC", "449901", "Marine Engineering Organizations", ()),  # SURVEYORS-MARINE
    ("SIC", "449910", "Marine Engineering Organizations", ()),  # SHIP REGISTERS
    ("SIC", "874225", "Marine Engineering Organizations", ()),  # MARINE RESOURCE CONSULTANTS
    ("SIC", "874261", "Marine Engineering Organizations", ()),  # NAVIGATION CONSULTANTS
    ("SIC", "874812", "Marine Engineering Organizations", ()),  # SHIPPING CONSULTANTS
    ("SIC", "874843", "Marine Engineering Organizations", ()),  # MARINE CONSULTANTS
    ("SIC", "171164", "Offshore Wind", WIND_WORDS),  # WIND POWER
    ("SIC", "351102", "Offshore Wind", WIND_WORDS),  # GENERATORS-WIND POWERED (MFRS)
    ("SIC", "507416", "Offshore Wind", WIND_WORDS),  # WIND ENERGY SYSTEMS (WHLS)
    ("SIC", "138207", "Offshore Oil & Gas", ()),  # TECHNICAL CONSULTANTS-PLATFORM DRILLING
    ("SIC", "138918", "Offshore Oil & Gas", ()),  # OFFSHORE PLATFORMS/OIL
    ("SIC", "162936", "Offshore Oil & Gas", ()),  # OIL-OFFSHORE CONSTRUCTION
    ("SIC", "441298", "Water Transportation", ()),  # DEEP SEA-FOREIGN TRANSPORT OF FREIGHT
    ("SIC", "442401", "Water Transportation", ()),  # OCEAN-FREIGHT
    ("SIC", "442498", "Water Transportation", ()),  # DEEP SEA-DOMESTIC TRANSPORT OF FREIGHT
    ("SIC", "443298", "Water Transportation", ()),  # FREIGHT-TRANSPORT ON THE GREAT LAKES
    ("SIC", "444901", "Water Transportation", ()),  # BARGE LINES & TERMINALS
    ("SIC", "444906", "Water Transportation", ()),  # SHIPPING-OVERSEAS
    ("SIC", "444999", "Water Transportation", ()),  # WATER TRANSPORTATION OF FREIGHT NEC
    ("SIC", "448198", "Water Transportation", ()),  # DEEP SEA-PASSENGER TRANS-EXCEPT FERRY
    ("SIC", "448201", "Water Transportation", ()),  # FERRIES
    ("SIC", "448903", "Water Transportation", ()),  # STEAMSHIP COMPANIES
    ("SIC", "449203", "Water Transportation", ()),  # MARINE VESSEL MANAGEMENT
    ("SIC", "449911", "Water Transportation", ()),  # SHIP OWNERS & OPERATORS
    ("SIC", "444902", "Ports & Cargo", ()),  # SHIPPING AGENTS
    ("SIC", "448102", "Ports & Cargo", ()),  # STEAMSHIP TERMINAL COMPANIES
    ("SIC", "449103", "Ports & Cargo", ()),  # TERMINALS-RIVER & MARINE
    ("SIC", "449108", "Ports & Cargo", ()),  # MARINE CARGO HANDLING
    ("SIC", "472904", "Ports & Cargo", ()),  # STEAMSHIP AGENCIES
    ("SIC", "508803", "Ports & Cargo", ()),  # SHIP BROKERS (WHLS)
    ("SIC", "508830", "Ports & Cargo", ()),  # TUGBOAT & BARGE BROKERS (WHLS)
    ("SIC", "736107", "Ports & Cargo", ()),  # STEVEDORING CONTRACTORS
    ("SIC", "962105", "Ports & Cargo", ()),  # PORT SERVICES
    ("SIC", "172106", "Recreational Marine", ()),  # BOAT PAINTING & LETTERING
    ("SIC", "448902", "Recreational Marine", ()),  # BOATS-EXCURSIONS
    ("SIC", "448905", "Recreational Marine", ()),  # AIR BOATS
    ("SIC", "449301", "Recreational Marine", ()),  # BOAT MOORAGES
    ("SIC", "449302", "Recreational Marine", ()),  # BOAT STORAGE
    ("SIC", "449303", "Recreational Marine", ()),  # BOAT YARDS
    ("SIC", "449304", "Recreational Marine", ()),  # BOAT REPAIRING
    ("SIC", "449306", "Recreational Marine", ()),  # MARINAS
    ("SIC", "449307", "Recreational Marine", ()),  # YACHT HARBORS
    ("SIC", "449309", "Recreational Marine", ()),  # BOAT DOCKS
    ("SIC", "449311", "Recreational Marine", ()),  # YACHT RIGGING
    ("SIC", "449313", "Recreational Marine", ()),  # BOAT CLUBS
    ("SIC", "449903", "Recreational Marine", ()),  # BOAT LAUNCHING
    ("SIC", "449904", "Recreational Marine", ()),  # BOAT CLEANING
    ("SIC", "449905", "Recreational Marine", ()),  # BOAT TRANSPORTING
    ("SIC", "449909", "Recreational Marine", ()),  # BOATS-LIVERY
    ("SIC", "554106", "Recreational Marine", ()),  # MARINE SERVICE STATIONS
    ("SIC", "555101", "Recreational Marine", ()),  # ENGINES-MARINE
    ("SIC", "555102", "Recreational Marine", ()),  # BOAT COVERS TOPS & UPHOLSTERY
    ("SIC", "555103", "Recreational Marine", ()),  # BOAT EQUIPMENT & SUPPLIES
    ("SIC", "555104", "Recreational Marine", ()),  # BOAT DEALERS SALES & SERVICE
    ("SIC", "555105", "Recreational Marine", ()),  # HARDWARE-MARINE
    ("SIC", "555106", "Recreational Marine", ()),  # CANOES
    ("SIC", "555107", "Recreational Marine", ()),  # YACHTS
    ("SIC", "555108", "Recreational Marine", ()),  # PROPELLERS
    ("SIC", "555109", "Recreational Marine", ()),  # OUTBOARD MOTORS
    ("SIC", "555110", "Recreational Marine", ()),  # MARINE EQUIPMENT & SUPPLIES-REPAIRING
    ("SIC", "555112", "Recreational Marine", ()),  # OUTBOARD MOTORS-PARTS & REPAIR
    ("SIC", "555113", "Recreational Marine", ()),  # MARINE EQUIPMENT & SUPPLIES
    ("SIC", "555114", "Recreational Marine", ()),  # ANCHORS-MARINE
    ("SIC", "555115", "Recreational Marine", ()),  # LIFE PRESERVERS
    ("SIC", "555116", "Recreational Marine", ()),  # TRANSMISSIONS-MARINE
    ("SIC", "555117", "Recreational Marine", ()),  # ANCHORS
    ("SIC", "555118", "Recreational Marine", ()),  # LIFE RAFT INFLATION EQUIPMENT
    ("SIC", "555120", "Recreational Marine", ()),  # BOAT WINDOWS
    ("SIC", "555121", "Recreational Marine", ()),  # MARINE EQUIPMENT-USED & REBUILT
    ("SIC", "555122", "Recreational Marine", ()),  # KAYAKS
    ("SIC", "555123", "Recreational Marine", ()),  # OUTBOARD MOTORS-USED
    ("SIC", "555125", "Recreational Marine", ()),  # YACHT BROKERS
    ("SIC", "555126", "Recreational Marine", ()),  # BOAT PERFORMANCE & RACING EQUIPMENT
    ("SIC", "555127", "Recreational Marine", ()),  # MARINE ELECTRONICS
    ("SIC", "555128", "Recreational Marine", ()),  # BOAT DEALERS USED
    ("SIC", "555129", "Recreational Marine", ()),  # REFRIGERATION-MARINE
    ("SIC", "556102", "Recreational Marine", ()),  # TRAILERS-BOAT
    ("SIC", "573122", "Recreational Marine", ()),  # MARINE ELECTRONIC EQUIP & SUPLS-RETAIL
    ("SIC", "594156", "Recreational Marine", ()),  # JET SKI-DEALERS
    ("SIC", "729991", "Recreational Marine", ()),  # YACHT DOCUMENTATION
    ("SIC", "753216", "Recreational Marine", ()),  # BOAT & YACHT CUSTOMIZING
    ("SIC", "753217", "Recreational Marine", ()),  # BOAT RESTORATION
    ("SIC", "769403", "Recreational Marine", ()),  # OUTBOARD MOTORS-REPAIRING
    ("SIC", "799913", "Recreational Marine", ()),  # BOATS-RENTAL & CHARTER
    ("SIC", "799914", "Recreational Marine", ()),  # BOATING INSTRUCTION
    ("SIC", "799917", "Recreational Marine", ()),  # CANOE TRIP OUTFITTERS
    ("SIC", "799918", "Recreational Marine", ()),  # CANOES-RENTAL & CHARTER
    ("SIC", "799928", "Recreational Marine", ()),  # FISHING PARTIES
    ("SIC", "799961", "Recreational Marine", ()),  # SAILING INSTRUCTION
    ("SIC", "449312", "Marine Suppliers", ()),  # SHIP FUELING
    ("SIC", "449907", "Marine Suppliers", ()),  # BARGES-LEASED
    ("SIC", "501217", "Marine Suppliers", ()),  # TRAILERS-BOAT-WHOLESALE
    ("SIC", "506554", "Marine Suppliers", ()),  # MARINE-RADIO TELEPHONE EQUIPMENT (WHLS)
    ("SIC", "507818", "Marine Suppliers", ()),  # MARINE REFRIGERATION/AC-SALES/SVC (WHLS)
    ("SIC", "508805", "Marine Suppliers", ()),  # SHIP CHANDLERS (WHLS)
    ("SIC", "508811", "Marine Suppliers", ()),  # MARINE EQUIPMENT & SUPPLIES-WHOLESALE
    ("SIC", "508812", "Marine Suppliers", ()),  # MARINE ELECTRONIC EQUIP & SUPLS (WHLS)
    ("SIC", "508813", "Marine Suppliers", ()),  # NAUTICAL INSTRUMENTS (WHLS)
    ("SIC", "508815", "Marine Suppliers", ()),  # OCEANOGRAPHIC EQUIPMENT (WHLS)
    ("SIC", "508827", "Marine Suppliers", ()),  # YACHT PROVISIONING (WHLS)
    ("SIC", "509103", "Marine Suppliers", ()),  # BOAT DISTRIBUTORS (WHLS)
    ("SIC", "509105", "Marine Suppliers", ()),  # BOAT EQUIPMENT & SUPPLIES-WHOLESALE
    ("SIC", "509121", "Marine Suppliers", ()),  # BOAT BROKERS (WHLS)
    ("SIC", "509128", "Marine Suppliers", ()),  # BOAT COVERS TOPS & UPHOLSTERY-WHOLESALE
    ("SIC", "509155", "Marine Suppliers", ()),  # DOCK BUMPERS (WHLS)
    ("SIC", "509160", "Marine Suppliers", ()),  # SAILBOATS & SAILBOAT SUPPLIES (WHLS)
    ("SIC", "509161", "Marine Suppliers", ()),  # HARDWARE-MARINE-WHOLESALE
    ("SIC", "509163", "Marine Suppliers", ()),  # OUTBOARD MOTORS-WHOLESALE
    ("SIC", "519811", "Marine Suppliers", ()),  # PAINT & COATINGS-MARINE (WHLS)
    ("SIC", "521151", "Marine Suppliers", ()),  # BOAT BUILDERS-MATERIALS
    ("SIC", "091201", "Fishing & Maritime Education", ()),  # FISHERMEN-COMMERCIAL
    ("SIC", "091301", "Fishing & Maritime Education", ()),  # OYSTERS
    ("SIC", "091998", "Fishing & Maritime Education", ()),  # MISCELLANEOUS MARINE PRODUCTS
    ("SIC", "822101", "Fishing & Maritime Education", COLLEGE_WORDS),  # SCHOOLS-UNIVERSITIES & COLLEGES
    ("SIC", "822110", "Fishing & Maritime Education", COLLEGE_WORDS),  # ENGINEERING SCHOOLS
    ("SIC", "824922", "Fishing & Maritime Education", ()),  # NAVIGATION SCHOOLS
)

NAME_HEADERS = ("company name", "company", "business name", "conm", "coname", "name")


def keyword_pattern(keywords: tuple[str, ...]) -> re.Pattern[str] | None:
    """Match any keyword as a whole word ("sea" matches Sea Wind, not Seattle)."""
    if not keywords:
        return None
    return re.compile(r"\b(" + "|".join(re.escape(k) for k in keywords) + r")\b", re.IGNORECASE)


RULES: dict[tuple[str, str], list[tuple[str, re.Pattern[str] | None]]] = {}
for _system, _code, _category, _keywords in CODES:
    RULES.setdefault((_system, _code), []).append((_category, keyword_pattern(_keywords)))
NAICS_CODES = {code for system, code in RULES if system == "NAICS"}
SIC_CODES = {code for system, code in RULES if system == "SIC"}
CODE_IN_LINE = re.compile("|".join(sorted(NAICS_CODES | SIC_CODES)).encode())


def match(naics: list[str], sics: list[str], name: str) -> list[tuple[str, str]]:
    """Return (matched code label, category) pairs for one business."""
    hits = []
    keys = [("NAICS", c[:6]) for c in naics] + [("SIC", c) for c in sics]
    for system, code in dict.fromkeys(keys):
        for category, pattern in RULES.get((system, code), []):
            if pattern is None or pattern.search(name):
                hits.append((f"{system} {code}", category))
    return hits


def find_columns(header: list[str]) -> tuple[list[int], list[int], int]:
    """Locate the NAICS code columns, the SIC code columns and the company-name column."""
    lower = [h.strip().lower() for h in header]
    coded = [i for i, h in enumerate(lower) if "code" in h and "desc" not in h]
    naics = [i for i in coded if "naics" in lower[i]]
    sic = [i for i in coded if "sic" in lower[i]]
    name = next((lower.index(h) for h in NAME_HEADERS if h in lower), -1)
    if name < 0:
        name = next((i for i, h in enumerate(lower) if "company" in h or "business name" in h), -1)
    if not (naics or sic) or name < 0:
        raise SystemExit(
            "Could not find the industry-code and company-name columns. Send Claude this header line:\n"
            + ",".join(header)
        )
    return naics, sic, name


def iter_sources(path: Path) -> Iterator[tuple[str, IO[bytes]]]:
    """Yield (file name, binary stream) for each data file: one file, a folder, or a zip."""
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
    kept, read, bad = 0, 0, 0
    per_category: Counter[str] = Counter()
    header_out: list[str] | None = None
    started = time.time()
    with (
        zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as out_archive,
        out_archive.open("maritime_companies.csv", "w") as raw_out,
        io.TextIOWrapper(raw_out, encoding="utf-8-sig", newline="") as out,
    ):
        writer = csv.writer(out)
        for label, stream in iter_sources(source):
            lines = iter(stream)
            first = next(lines).decode("latin-1")
            delimiter = max((",", "\t", "|"), key=first.count)
            header = next(csv.reader([first], delimiter=delimiter))
            naics_cols, sic_cols, name_col = find_columns(header)
            if header_out is None:
                header_out = [*header, "SHI Categories", "SHI Matched Codes", "Source File"]
                writer.writerow(header_out)
                print(f"Columns: name = {header[name_col]!r}; NAICS = {[header[i] for i in naics_cols]}")
                print(f"         SIC = {[header[i] for i in sic_cols]}")
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
                    naics = [row[i].strip() for i in naics_cols if i < len(row) and row[i].strip()]
                    sics = [row[i].strip() for i in sic_cols if i < len(row) and row[i].strip()]
                    hits = match(naics, sics, row[name_col])
                except (StopIteration, IndexError, csv.Error):
                    bad += 1
                    continue
                if not hits:
                    continue
                categories = sorted({category for _, category in hits})
                per_category.update(categories)
                matched = "; ".join(dict.fromkeys(code for code, _ in hits))
                writer.writerow([*row, "; ".join(categories), matched, label])
                kept += 1
                file_kept += 1
            elapsed = time.time() - started
            print(f"  {label}: kept {file_kept:,}  (total {kept:,} of {read:,} read, {elapsed:.0f}s)")
    print(f"\nDone: kept {kept:,} maritime businesses out of {read:,}; {bad:,} unreadable lines skipped.")
    for category, n in per_category.most_common():
        print(f"  {category}: {n:,}")
    print(f"\nUpload this file to Claude: {out_zip}  ({out_zip.stat().st_size / 1e6:.1f} MB)")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit('Usage: python filter_maritime_bulk.py "C:\\path\\to\\data file.txt"')
    source = Path(sys.argv[1])
    if not source.exists():
        raise SystemExit(f"File not found: {source}")
    out_zip = source.with_name(source.stem + "_maritime.zip") if source.is_file() else source / "maritime.zip"
    print(f"Reading {source}\nThis can take 20-60 minutes for the full U.S. file. Leave this window open.\n")
    run(source, out_zip)


if __name__ == "__main__":
    main()
