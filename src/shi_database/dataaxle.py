"""Minimal client for the Data Axle Platform Places (business) search API."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

DEFAULT_BASE_URL = "https://api.data-axle.com/v1/places/search"
DEFAULT_PAGE_SIZE = 400
DEFAULT_MAX_WINDOW = 4000
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
MAX_RETRIES = 4

# Keep the state table compact rather than one code per line.
# fmt: off
US_STATES = (
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI", "ID", "IL",
    "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE",
    "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD",
    "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "PR", "GU", "VI",
)
# fmt: on

Record = dict[str, Any]


class DataAxleError(RuntimeError):
    """Raised when the Data Axle API returns an unrecoverable error."""


@dataclass(frozen=True)
class QuerySpec:
    """One logical Data Axle query: a NAICS code, optional keyword and state.

    Attributes:
        naics_code: Six-digit NAICS code.
        keyword: Optional free-text query sent as the API ``query`` parameter.
        state: Optional two-letter state; None means nationwide.
    """

    naics_code: str
    keyword: str | None = None
    state: str | None = None


@dataclass
class DataAxleClient:
    """Paginated client for Data Axle Places search.

    Attributes:
        token: Data Axle API token (sent as the X-AUTH-TOKEN header).
        naics_attribute: Places attribute holding NAICS codes in the filter DSL.
        base_url: Search endpoint URL.
        packages: Data Axle field packages to request.
        page_size: Records per request.
        max_window: Largest offset+limit the endpoint allows per query.
    """

    token: str
    naics_attribute: str = "naics_codes"
    base_url: str = DEFAULT_BASE_URL
    packages: list[str] = field(default_factory=lambda: ["standard_v1"])
    page_size: int = DEFAULT_PAGE_SIZE
    max_window: int = DEFAULT_MAX_WINDOW

    def __post_init__(self) -> None:
        """Validate configuration up front."""
        if not self.token:
            raise ValueError("A Data Axle API token is required")
        if not 0 < self.page_size <= self.max_window:
            raise ValueError(f"page_size must be in 1..{self.max_window}, got {self.page_size}")

    def build_body(self, spec: QuerySpec, offset: int, limit: int) -> dict[str, Any]:
        """Build the JSON request body for one page of a query.

        Args:
            spec: The query to run.
            offset: Zero-based record offset.
            limit: Number of records to return.

        Returns:
            Request body ready for JSON encoding.
        """
        propositions: list[dict[str, Any]] = [
            {"relation": "in", "attribute": self.naics_attribute, "value": [spec.naics_code]},
        ]
        if spec.state:
            propositions.append({"relation": "equals", "attribute": "state", "value": spec.state})
        body: dict[str, Any] = {
            "filter": {"connective": "and", "propositions": propositions},
            "limit": limit,
            "offset": offset,
            "packages": self.packages,
        }
        if spec.keyword:
            body["query"] = spec.keyword
        return body

    def count(self, spec: QuerySpec) -> int:
        """Return the total number of matches for a query without paging."""
        response = self._post(self.build_body(spec, offset=0, limit=1))
        return int(response.get("count", 0))

    def iter_records(self, spec: QuerySpec) -> Iterator[Record]:
        """Yield every record for a query, splitting by state when needed.

        Nationwide queries whose count exceeds ``max_window`` are re-run
        state by state so that no records are silently dropped.

        Args:
            spec: The query to run.

        Yields:
            Raw Data Axle place documents.
        """
        total = self.count(spec)
        if total > self.max_window and spec.state is None:
            for state in US_STATES:
                yield from self.iter_records(QuerySpec(spec.naics_code, spec.keyword, state))
            return
        if total > self.max_window:
            print(f"warning: {spec} has {total} matches; only first {self.max_window} retrievable")
        yield from self._iter_pages(spec, min(total, self.max_window))

    def _iter_pages(self, spec: QuerySpec, total: int) -> Iterator[Record]:
        """Yield records page by page up to ``total``."""
        for offset in range(0, total, self.page_size):
            limit = min(self.page_size, total - offset)
            response = self._post(self.build_body(spec, offset, limit))
            documents = response.get("documents", [])
            yield from documents
            if len(documents) < limit:
                return

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        """POST a body with retry on rate-limit and transient server errors."""
        request = urllib.request.Request(  # noqa: S310 - URL is the fixed Data Axle https endpoint
            self.base_url,
            data=json.dumps(body).encode("utf-8"),
            headers={"X-AUTH-TOKEN": self.token, "Content-Type": "application/json"},
            method="POST",
        )
        for attempt in range(MAX_RETRIES + 1):
            try:
                with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - see above
                    return dict(json.load(response))
            except urllib.error.HTTPError as error:
                if error.code not in RETRYABLE_STATUS or attempt == MAX_RETRIES:
                    detail = error.read().decode("utf-8", errors="replace")[:500]
                    raise DataAxleError(f"HTTP {error.code}: {detail}") from error
            time.sleep(2 ** (attempt + 1))
        raise DataAxleError("retries exhausted")  # unreachable; satisfies type checker
