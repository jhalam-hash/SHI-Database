# SHI Database

Builds a list of U.S. marine-industry companies from the
[Data Axle](https://www.data-axle.com/data-solutions/apis/) business (Places)
database, organized by NAICS code. It covers these categories:

| Category | Core NAICS (pulled in full) | Broad NAICS (narrowed by marine keywords) |
|---|---|---|
| Shipyards | 336611 Ship Building & Repairing, 336612 Boat Building | — |
| Maritime Contractors | 488310 Port & Harbor Ops, 488330 Navigational Services, 488390 Other Water Transport Support | 237990 Heavy/Civil (marine construction, dredging), 811310 Machinery Repair, 333618 Engines, 334511 Navigation/Sonar Systems |
| Independent Design Firms | — | 541330 Engineering Services, 541310 Architectural Services, 541490 Specialized Design |
| Government Design Organizations | — | 928110 National Security (NAVSEA, NSWC Carderock, SUPSHIP), 926120 Transportation Programs (MARAD) |
| Hydrodynamics Specialists | — | 541715 Physical/Engineering R&D, 541380 Testing Labs, 541690 Scientific & Technical Consulting |
| Marine Engineering Organizations | — | 541370 Surveying & Mapping (hydrographic), 541990 Other Professional Services, 813920 Professional Orgs (SNAME, ASNE), 813910 Business Associations |
| Offshore Wind | — | 221115 Wind Power Generation, 237130 Power Line Construction (subsea cable install), 333611 Turbine Mfg, 335929 Energy Wire Mfg (subsea cable) |
| Offshore Oil & Gas | — | 211120 Crude Petroleum Extraction, 213111 Drilling Wells, 213112 Oil & Gas Support, 541360 Geophysical Surveying |
| Water Transportation | 483111–483114 Deep Sea, Coastal & Great Lakes, 483211–483212 Inland Water | — |
| Ports & Cargo | 488320 Marine Cargo Handling | 488510 Freight Transportation Arrangement |
| Recreational Marine | 713930 Marinas, 441222 Boat Dealers, 487210 Scenic Water Transportation | 811490 Other Repair (boat repair) |
| Marine Suppliers | — | 423860 Transportation Equipment Wholesalers, 532411 Vessel Rental & Leasing |
| Fishing & Maritime Education | 114111 Finfish Fishing, 114112 Shellfish Fishing | 611310 Colleges (maritime academies) |

The full table, with notes on each code, is in
[`data/marine_naics_codes.csv`](data/marine_naics_codes.csv). Edit it to add or remove codes.

**Why two tiers:** no NAICS code covers "naval architect" or "hydrodynamics" on its
own. Those firms sit inside large general codes such as 541330 Engineering Services,
which has well over 100k U.S. establishments. For each *broad* code, the tool runs one
Data Axle query per marine keyword (`marine`, `naval`, `ship`, `hydrodynamic`,
`offshore`, ...; see `MARINE_QUERY_KEYWORDS` in `src/shi_database/records.py`). A broad
code can list its own keywords in the CSV's `keywords` column (semicolon-separated); the
offshore wind codes, for example, use `offshore wind`, `floating wind`, `offshore` and
`subsea` so they don't pull in every onshore wind farm.
*Core* codes are pulled in full.

## Usage

Requires Python 3.10+ with the standard library only, plus a Data Axle Platform API token.

```bash
export DATA_AXLE_API_TOKEN=...            # your Data Axle key

# 1. Preview the 391 request bodies without calling the API
PYTHONPATH=src python -m shi_database.cli --dry-run

# 2. Check match counts per query (cheap; 1 record per call)
PYTHONPATH=src python -m shi_database.cli --counts-only

# 3. Full pull → output/us_marine_companies.csv
PYTHONPATH=src python -m shi_database.cli

# Only some categories
PYTHONPATH=src python -m shi_database.cli --category Shipyards --category "Hydrodynamics Specialists"
```

Output columns: name, address, phone, website, lat/long, employees, sales volume,
NAICS codes, `shi_categories` (every category whose query found the company),
`matched_naics`, `matched_keywords`, and `name_has_marine_term`. That last flag helps
you review keyword-query hits by hand. Companies found by several queries are merged
on Data Axle's `infogroup_id`.

When a nationwide query returns more records than the search endpoint can page through
(4,000 by default), the tool re-runs it state by state, covering all states plus DC, PR, GU and VI.

## Building the workbook from Reference Solutions exports

If you have Data Axle through a library subscription (Data Axle Reference Solutions,
formerly ReferenceUSA) instead of an API key, export "Detail" spreadsheets from the web
interface and build the workbook from them. This step needs `openpyxl`:

```bash
pip install openpyxl
PYTHONPATH=src python -m shi_database.workbook ~/Downloads/Detail*.xlsx
# → output/us_marine_companies.xlsx
```

The importer matches each company's Primary NAICS and NAICS 1-10 columns (the first
6 digits of Data Axle's 8-digit codes) against `data/marine_naics_codes.csv`. It
de-duplicates on IUSA Number and writes these tabs:

- **Summary:** counts by category, SHI NAICS code, primary NAICS and state, as live formulas, plus the export date and method.
- **One tab per SHI category.**
- **Not in SHI NAICS:** exported companies with no matching code.
- **All Companies.**

Rows matched only through *broad* codes whose name has no marine term are highlighted
yellow (`Needs Review = yes`). Reference Solutions caps the rows per download, so export
each search in full (several files are fine) and search by the SHI NAICS codes above.

## Things to confirm against your Data Axle account

These settings come from public integrations, not Data Axle's official API reference, so
check them with `--counts-only` on a small category first:

- **Endpoint/auth:** `POST https://api.data-axle.com/v1/places/search` with an
  `X-AUTH-TOKEN` header.
- **NAICS filter attribute:** the default is `naics_codes`. If counts come back as 0,
  pass the attribute name from your account's docs with `--naics-attribute`. Reference
  Solutions exports (October 2026) confirm that Data Axle stores NAICS as **8-digit**
  codes (e.g. `48311101`), so the API filter may need 8-digit values or a prefix match.
- **Packages:** the default is `standard_v1`. Change it with `--package` if your
  subscription uses different field packages.
- **Paging window:** `DEFAULT_MAX_WINDOW` in `dataaxle.py` (4,000).

## Development

```bash
pip install pytest ruff mypy openpyxl types-openpyxl
python -m pytest && ruff check . && ruff format --check . && python -m mypy --strict src tests
```
