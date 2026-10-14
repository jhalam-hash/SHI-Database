"""Command-line entry point: pull U.S. marine-industry companies from Data Axle."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

from shi_database.dataaxle import DataAxleClient, DataAxleError, QuerySpec
from shi_database.naics import NaicsTarget, load_naics_targets
from shi_database.records import MARINE_QUERY_KEYWORDS, OUTPUT_COLUMNS, CompanyIndex

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_NAICS_TABLE = REPO_ROOT / "data" / "marine_naics_codes.csv"
DEFAULT_OUTPUT = REPO_ROOT / "output" / "us_marine_companies.csv"
TOKEN_ENV_VAR = "DATA_AXLE_API_TOKEN"  # noqa: S105 - env var name, not a secret


def build_query_plan(targets: list[NaicsTarget]) -> list[tuple[NaicsTarget, QuerySpec]]:
    """Expand NAICS targets into the concrete queries to run.

    Core codes are pulled in full; broad codes get one query per keyword (the
    code's own keywords if the table lists any, else the marine keyword list).

    Args:
        targets: NAICS targets to query.

    Returns:
        (target, query) pairs in execution order.
    """
    plan: list[tuple[NaicsTarget, QuerySpec]] = []
    for target in targets:
        if not target.is_broad:
            plan.append((target, QuerySpec(target.code)))
            continue
        keywords = target.keywords or MARINE_QUERY_KEYWORDS
        plan.extend((target, QuerySpec(target.code, keyword)) for keyword in keywords)
    return plan


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--naics-table", type=Path, default=DEFAULT_NAICS_TABLE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--category", action="append", help="Limit to a category (repeatable)")
    parser.add_argument(
        "--naics-attribute",
        default="naics_codes",
        help="Places filter attribute holding NAICS codes (default: naics_codes)",
    )
    parser.add_argument("--package", action="append", help="Data Axle package (default: standard_v1)")
    parser.add_argument("--dry-run", action="store_true", help="Print request bodies; make no API calls")
    parser.add_argument("--counts-only", action="store_true", help="Report match counts per query only")
    return parser.parse_args(argv)


def write_csv(rows: list[dict[str, str]], path: Path) -> None:
    """Write output rows to CSV, creating the parent directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def run(args: argparse.Namespace) -> int:
    """Execute the pull described by parsed arguments and return an exit code."""
    targets = load_naics_targets(args.naics_table, set(args.category) if args.category else None)
    plan = build_query_plan(targets)
    token = os.environ.get(TOKEN_ENV_VAR, "")
    if args.dry_run:
        token = token or "dry-run"
    elif not token:
        print(f"error: set {TOKEN_ENV_VAR} to your Data Axle API token", file=sys.stderr)
        return 2

    client = DataAxleClient(token, args.naics_attribute, packages=args.package or ["standard_v1"])
    if args.dry_run:
        for _, spec in plan:
            print(json.dumps(client.build_body(spec, offset=0, limit=client.page_size)))
        print(f"{len(plan)} queries planned", file=sys.stderr)
        return 0
    if args.counts_only:
        for target, spec in plan:
            print(f"{target.category}\t{spec.naics_code}\t{spec.keyword or '*'}\t{client.count(spec)}")
        return 0

    index = CompanyIndex()
    for number, (target, spec) in enumerate(plan, start=1):
        print(
            f"[{number}/{len(plan)}] {target.category} {spec.naics_code} {spec.keyword or '*'}",
            file=sys.stderr,
        )
        for document in client.iter_records(spec):
            index.add(document, target.category, spec.naics_code, spec.keyword)
    write_csv(index.rows(), args.output)
    print(f"wrote {len(index)} unique companies to {args.output}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the CLI, converting expected failures into a non-zero exit code."""
    args = parse_args(argv)
    try:
        return run(args)
    except (DataAxleError, FileNotFoundError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
