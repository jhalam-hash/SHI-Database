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

The full table, with notes on each code, is in
[`data/marine_naics_codes.csv`](data/marine_naics_codes.csv). Edit it to add or remove codes.

**Why two tiers:** no NAICS code covers "naval architect" or "hydrodynamics" on its
own. Those firms sit inside large general codes such as 541330 Engineering Services,
which has well over 100k U.S. establishments. For each *broad* code, the tool runs one
Data Axle query per marine keyword (`marine`, `naval`, `ship`, `hydrodynamic`,
`offshore`, ...; see `MARINE_QUERY_KEYWORDS` in `src/shi_database/records.py`).
*Core* codes are pulled in full.

## Usage

Requires Python 3.10+ with the standard library only, plus a Data Axle Platform API token.

```bash
export DATA_AXLE_API_TOKEN=...            # your Data Axle key

# 1. Preview the 309 request bodies without calling the API
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

## Things to confirm against your Data Axle account

These settings come from public integrations, not Data Axle's official API reference, so
check them with `--counts-only` on a small category first:

- **Endpoint/auth:** `POST https://api.data-axle.com/v1/places/search` with an
  `X-AUTH-TOKEN` header.
- **NAICS filter attribute:** the default is `naics_codes`. If counts come back as 0,
  pass the attribute name from your account's docs with `--naics-attribute`. Data Axle
  stores some NAICS values as 8-digit codes; if so, add those codes to the CSV.
- **Packages:** the default is `standard_v1`. Change it with `--package` if your
  subscription uses different field packages.
- **Paging window:** `DEFAULT_MAX_WINDOW` in `dataaxle.py` (4,000).

## Development

```bash
pip install pytest ruff mypy
python -m pytest && ruff check . && ruff format --check . && python -m mypy --strict src tests
```
