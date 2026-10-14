"""Normalize, flag and de-duplicate Data Axle place records."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

# Sent as the Data Axle ``query`` parameter for "broad" NAICS codes, whose
# members are mostly non-marine (e.g. 541330 Engineering Services).
MARINE_QUERY_KEYWORDS = (
    "marine",
    "maritime",
    "naval",
    "navy",
    "ship",
    "shipyard",
    "boat",
    "yacht",
    "vessel",
    "offshore",
    "subsea",
    "ocean",
    "hydrodynamic",
    "hydrographic",
    "harbor",
    "dredging",
    "towing tank",
    "propeller",
    "coast guard",
)

_MARINE_NAME_PATTERN = re.compile(
    r"\b(marine|maritime|naval|navy|navsea|ship\w*|boat\w*|yacht\w*|vessel\w*|hull|"
    r"offshore|subsea|ocean\w*|hydro\w*|harbou?r|port|dock\w*|dredg\w*|propeller\w*|"
    r"sonar|coast guard|carderock|seakeeping|tug\w*|barge\w*|nautic\w*)\b",
    re.IGNORECASE,
)

OUTPUT_COLUMNS = (
    "infogroup_id",
    "name",
    "street",
    "city",
    "state",
    "postal_code",
    "phone",
    "website",
    "latitude",
    "longitude",
    "employees",
    "sales_volume",
    "naics_codes",
    "shi_categories",
    "matched_naics",
    "matched_keywords",
    "name_has_marine_term",
)

# Data Axle field names have varied between packages; try each in order.
_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "infogroup_id": ("infogroup_id", "id"),
    "name": ("name", "company_name"),
    "street": ("street", "address"),
    "city": ("city",),
    "state": ("state",),
    "postal_code": ("postal_code", "zip"),
    "phone": ("phone",),
    "website": ("website", "url"),
    "latitude": ("latitude",),
    "longitude": ("longitude",),
    "employees": ("location_employee_count", "employee_count", "employees"),
    "sales_volume": ("location_sales_volume", "sales_volume"),
    "naics_codes": ("naics_codes", "naics_code_ids", "primary_naics_code"),
}


def name_has_marine_term(name: str) -> bool:
    """Return True if a business name contains a marine-industry term."""
    return bool(_MARINE_NAME_PATTERN.search(name))


def normalize_record(document: dict[str, Any]) -> dict[str, str]:
    """Flatten a raw Data Axle document into the output column set.

    Args:
        document: Raw place document from the search API.

    Returns:
        Mapping of base output columns to string values (empty if absent).
    """
    row = {column: _first_present(document, aliases) for column, aliases in _FIELD_ALIASES.items()}
    row["name_has_marine_term"] = "yes" if name_has_marine_term(row["name"]) else "no"
    return row


def _first_present(document: dict[str, Any], aliases: Iterable[str]) -> str:
    """Return the first non-empty aliased field from a document as a string."""
    for alias in aliases:
        value = document.get(alias)
        if value in (None, "", []):
            continue
        if isinstance(value, list):
            return ";".join(str(item) for item in value)
        return str(value)
    return ""


class CompanyIndex:
    """Accumulate records, merging duplicates hit by several queries."""

    def __init__(self) -> None:
        """Create an empty index."""
        self._rows: dict[str, dict[str, str]] = {}
        self._tags: dict[str, dict[str, set[str]]] = {}

    def add(self, document: dict[str, Any], category: str, naics: str, keyword: str | None) -> None:
        """Add one raw document, tagging it with what query found it.

        Args:
            document: Raw place document.
            category: SHI category of the NAICS target that matched.
            naics: NAICS code that matched.
            keyword: Keyword query used, or None for an unfiltered pull.
        """
        row = normalize_record(document)
        key = row["infogroup_id"] or "|".join((row["name"], row["street"], row["postal_code"])).lower()
        self._rows.setdefault(key, row)
        tags = self._tags.setdefault(key, {"categories": set(), "naics": set(), "keywords": set()})
        tags["categories"].add(category)
        tags["naics"].add(naics)
        if keyword:
            tags["keywords"].add(keyword)

    def __len__(self) -> int:
        """Return the number of unique companies."""
        return len(self._rows)

    def rows(self) -> list[dict[str, str]]:
        """Return merged output rows sorted by state, city and name."""
        merged = []
        for key, row in self._rows.items():
            tags = self._tags[key]
            merged.append(
                {
                    **row,
                    "shi_categories": ";".join(sorted(tags["categories"])),
                    "matched_naics": ";".join(sorted(tags["naics"])),
                    "matched_keywords": ";".join(sorted(tags["keywords"])),
                }
            )
        return sorted(merged, key=lambda r: (r["state"], r["city"], r["name"].lower()))
