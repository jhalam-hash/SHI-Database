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


def test_codes_match_data_tables() -> None:
    codes = _load_tool().CODES
    with DEFAULT_NAICS_TABLE.open(newline="", encoding="utf-8") as handle:
        core = {(r["naics_code"], r["category"]) for r in csv.DictReader(handle) if r["tier"] == "core"}
    sic_table = DEFAULT_NAICS_TABLE.with_name("maritime_sic_codes.csv")
    with sic_table.open(newline="", encoding="utf-8") as handle:
        sic = {(r["sic_code"], r["category"], bool(r["keywords"])) for r in csv.DictReader(handle)}
    tool_naics = {(code, cat) for system, code, cat, kws in codes if system == "NAICS" and not kws}
    tool_sic = {(code, cat, bool(kws)) for system, code, cat, kws in codes if system == "SIC"}
    assert tool_naics == core
    assert tool_sic == sic


def test_match_uses_codes_and_keywords_only_for_wind_and_colleges() -> None:
    tool = _load_tool()
    assert tool.match(["33661101"], [], "Anything Inc") == [("NAICS 336611", "Shipyards")]
    design = tool.match(["54133006"], ["871101"], "Smith Associates")
    assert design == [("SIC 871101", "Independent Design Firms")]
    assert tool.match(["54133006"], ["871106"], "Smith Marine Engineering") == []
    assert tool.match(["22111501"], ["171164"], "Prairie Wind Farm") == []
    assert [c for _, c in tool.match(["22111501"], [], "Atlantic Offshore Wind")] == ["Offshore Wind"]
    assert tool.match(["61131009"], ["822101"], "State University") == []
    academy = tool.match([], ["822101"], "Maine Maritime Academy")
    assert academy == [("SIC 822101", "Fishing & Maritime Education")]


def test_list_industry_codes_finds_naics_and_sic_columns() -> None:
    path = TOOL.with_name("list_industry_codes.py")
    spec = importlib.util.spec_from_file_location("list_industry_codes", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    header = [
        "COMPANY",
        "PRIMARY SIC CODE",
        "SIC6_DESCRIPTIONS",
        "PRIMARY NAICS CODE",
        "NAICS8 DESCRIPTIONS",
        "SIC CODE 1",
        "SIC6_DESCRIPTIONS (SIC1)",
        "ZIPCODE",
    ]
    assert module.code_columns(header) == [("SIC", 1, 2, True), ("NAICS", 3, 4, True), ("SIC", 5, 6, False)]
