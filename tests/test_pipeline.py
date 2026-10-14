"""Offline tests for the NAICS table, query plan and record handling."""

from __future__ import annotations

from pathlib import Path

import pytest

from shi_database.cli import DEFAULT_NAICS_TABLE, build_query_plan
from shi_database.dataaxle import DataAxleClient, QuerySpec
from shi_database.naics import load_naics_targets
from shi_database.records import MARINE_QUERY_KEYWORDS, CompanyIndex, name_has_marine_term


def test_load_naics_targets_covers_all_categories() -> None:
    targets = load_naics_targets(DEFAULT_NAICS_TABLE)
    categories = {target.category for target in targets}
    assert categories == {
        "Shipyards",
        "Maritime Contractors",
        "Independent Design Firms",
        "Government Design Organizations",
        "Hydrodynamics Specialists",
        "Marine Engineering Organizations",
    }
    assert any(target.code == "336611" and not target.is_broad for target in targets)


def test_load_naics_targets_rejects_unknown_category() -> None:
    with pytest.raises(ValueError, match="Unknown categories"):
        load_naics_targets(DEFAULT_NAICS_TABLE, {"Airports"})


def test_load_naics_targets_rejects_bad_code(tmp_path: Path) -> None:
    table = tmp_path / "bad.csv"
    table.write_text("category,naics_code,naics_title,tier\nX,3366,Bad,core\n", encoding="utf-8")
    with pytest.raises(ValueError, match="6 digits"):
        load_naics_targets(table)


def test_build_query_plan_expands_broad_codes_by_keyword() -> None:
    targets = load_naics_targets(DEFAULT_NAICS_TABLE, {"Shipyards", "Independent Design Firms"})
    plan = build_query_plan(targets)
    core = [spec for _, spec in plan if spec.keyword is None]
    assert {spec.naics_code for spec in core} == {"336611", "336612"}
    assert len(plan) == len(core) + 3 * len(MARINE_QUERY_KEYWORDS)


def test_build_body_includes_naics_state_and_keyword() -> None:
    client = DataAxleClient("token")
    body = client.build_body(QuerySpec("541330", "naval", "VA"), offset=400, limit=400)
    propositions = body["filter"]["propositions"]
    assert {"relation": "in", "attribute": "naics_codes", "value": ["541330"]} in propositions
    assert {"relation": "equals", "attribute": "state", "value": "VA"} in propositions
    assert body["query"] == "naval"
    assert body["offset"] == 400


def test_name_has_marine_term_uses_word_boundaries() -> None:
    assert name_has_marine_term("Bath Iron Works Shipyard")
    assert name_has_marine_term("Gulf Coast Port Authority")
    assert not name_has_marine_term("Midwest Transport Support LLC")


def test_company_index_merges_duplicate_hits() -> None:
    index = CompanyIndex()
    document = {"infogroup_id": "1", "name": "Acme Naval Architects", "state": "VA", "city": "Norfolk"}
    index.add(document, "Independent Design Firms", "541330", "naval")
    index.add(document, "Hydrodynamics Specialists", "541715", "hydrodynamic")
    rows = index.rows()
    assert len(rows) == 1
    assert rows[0]["matched_naics"] == "541330;541715"
    assert rows[0]["shi_categories"] == "Hydrodynamics Specialists;Independent Design Firms"
    assert rows[0]["name_has_marine_term"] == "yes"
