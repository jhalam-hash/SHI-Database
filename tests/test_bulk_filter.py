"""The standalone bulk filter must use the same codes and keywords as the NAICS table."""

from __future__ import annotations

import csv
import importlib.util
from pathlib import Path
from types import ModuleType

from shi_database.cli import DEFAULT_NAICS_TABLE

TOOL = Path(__file__).resolve().parents[1] / "tools" / "filter_maritime_bulk.py"


def _load_tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("filter_maritime_bulk", TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_targets_match_naics_table() -> None:
    with DEFAULT_NAICS_TABLE.open(newline="", encoding="utf-8") as handle:
        table = [
            (r["naics_code"], r["category"], r["tier"], tuple(k for k in r["keywords"].split(";") if k))
            for r in csv.DictReader(handle)
        ]
    assert list(_load_tool().TARGETS) == table


def test_match_applies_core_and_keyword_rules() -> None:
    tool = _load_tool()
    assert tool.match(["336611"], "Anything Inc") == [("336611", "Shipyards")]
    assert tool.match(["488510"], "Acme Transport") == []
    assert tool.match(["488510"], "Ocean Freight") == [("488510", "Ports & Cargo")]
    assert tool.match(["541330"], "Smith Engineering") == []
