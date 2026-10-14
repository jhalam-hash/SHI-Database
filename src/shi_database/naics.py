"""Load the marine-industry NAICS code table used to drive Data Axle queries."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

VALID_TIERS = frozenset({"core", "broad"})
REQUIRED_COLUMNS = ("category", "naics_code", "naics_title", "tier")


@dataclass(frozen=True)
class NaicsTarget:
    """One NAICS code to pull from Data Axle.

    Attributes:
        category: SHI target category (e.g. "Shipyards").
        code: Six-digit 2022 NAICS code.
        title: Official NAICS title.
        tier: "core" if every business under the code is marine-related,
            "broad" if results must be narrowed with marine keywords.
        keywords: Search keywords for a broad code; empty means the default
            marine keyword list.
    """

    category: str
    code: str
    title: str
    tier: str
    keywords: tuple[str, ...] = ()

    @property
    def is_broad(self) -> bool:
        """Return True when results need marine keyword narrowing."""
        return self.tier == "broad"


def load_naics_targets(path: Path, categories: set[str] | None = None) -> list[NaicsTarget]:
    """Load NAICS targets from the reference CSV.

    Args:
        path: Path to ``marine_naics_codes.csv``.
        categories: Optional set of category names to keep; None keeps all.

    Returns:
        Targets in file order, filtered to the requested categories.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ValueError: If the file is missing columns or has a malformed row.
    """
    if not path.is_file():
        raise FileNotFoundError(f"NAICS table not found: {path}")

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = [col for col in REQUIRED_COLUMNS if col not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path} is missing columns: {missing}")
        targets = [_parse_row(row, line_no) for line_no, row in enumerate(reader, start=2)]

    if categories is None:
        return targets
    unknown = categories - {target.category for target in targets}
    if unknown:
        raise ValueError(f"Unknown categories: {sorted(unknown)}")
    return [target for target in targets if target.category in categories]


def _parse_row(row: dict[str, str], line_no: int) -> NaicsTarget:
    """Validate and convert one CSV row into a NaicsTarget."""
    code = row["naics_code"].strip()
    tier = row["tier"].strip().lower()
    if len(code) != 6 or not code.isdigit():
        raise ValueError(f"line {line_no}: NAICS code must be 6 digits, got {code!r}")
    if tier not in VALID_TIERS:
        raise ValueError(f"line {line_no}: tier must be one of {sorted(VALID_TIERS)}, got {tier!r}")
    return NaicsTarget(
        category=row["category"].strip(),
        code=code,
        title=row["naics_title"].strip(),
        tier=tier,
        keywords=tuple(word.strip() for word in (row.get("keywords") or "").split(";") if word.strip()),
    )
