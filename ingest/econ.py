"""Seattle-area inflation and Washington population, for per-resident, inflation-
adjusted comparisons (DECISIONS D-047).

Both come from ERFC's quarterly Economic & Revenue Forecast publication:
- "Seattle Cons. Price Index (1982-84=1.0)" by fiscal year (Table 2.1)
- "Total Population" by year (population table; OFM-based, April 1)

Each September edition covers about eight years; earlier years in an edition are
history, later ones forecast. For each year we take the newest edition, and mark
years beyond the newest edition's own year as forecast.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .budget_to_actual import pdf_text
from .common import SAMPLES, fetch, write_csv

ERFC = "https://erfc.wa.gov/sites/default/files/"
# (edition year, url): oldest first; newer editions overwrite older values.
EDITIONS = [
    (2020, ERFC + "2025-03/sep20pub.pdf"),
    (2022, ERFC + "2025-03/sep22pub.pdf"),
    (2024, ERFC + "2025-03/sept24pub.pdf"),
    (2026, ERFC + "2026-10/sep26pub.pdf"),
]
NUM = r"-?[\d,]+(?:\.\d+)?"


@dataclass
class EconValue:
    series: str  # seattle_cpi_fy | population
    year: int
    value: float
    edition: int
    forecast: bool


def _year_header(lines: list[str], i: int) -> list[int] | None:
    """The nearest line above i that lists at least six years."""
    for j in range(i, max(i - 40, -1), -1):
        years = [int(y) for y in re.findall(r"\b(20\d\d)\b", lines[j])]
        if len(years) >= 6 and all(b == a + 1 for a, b in zip(years, years[1:])):
            return years
    return None


def parse_edition(text: str, edition: int) -> list[EconValue]:
    lines = text.splitlines()
    out: list[EconValue] = []
    targets = {"seattle_cpi_fy": re.compile(r"^\s*Seattle Cons\. Price Index \(1982-84=1\.0\)\s+(.*)$"),
               "population": re.compile(r"^\s*Total Population\s+(.*)$")}
    seen: set[str] = set()
    for i, line in enumerate(lines):
        for series, rx in targets.items():
            m = rx.match(line)
            if not m or series in seen:
                continue
            nums = [float(x.replace(",", "")) for x in re.findall(NUM, m.group(1))]
            years = _year_header(lines, i)
            if not years or len(nums) < len(years):
                continue
            seen.add(series)
            for y, v in zip(years, nums[:len(years)]):
                out.append(EconValue(series, y, v, edition, forecast=y > edition))
    return out


def load() -> dict[str, dict[int, EconValue]]:
    series: dict[str, dict[int, EconValue]] = {}
    latest = max(e for e, _ in EDITIONS)
    for edition, url in EDITIONS:
        path = fetch(url, "econ", url.rsplit("/", 1)[-1])
        for v in parse_edition(pdf_text(path), edition):
            # Newer editions win; forecast status is judged against the newest edition.
            v.forecast = v.year > latest
            series.setdefault(v.series, {})[v.year] = v
    return series


def run() -> None:
    series = load()
    for name, vals in series.items():
        ys = sorted(vals)
        print(f"{name}: {ys[0]}-{ys[-1]} ({sum(1 for y in ys if vals[y].forecast)} forecast years)")
    if set(series) != {"seattle_cpi_fy", "population"}:
        raise ValueError(f"missing series: {set(series)}")
    write_csv(SAMPLES / "econ.csv", [asdict(v) for vals in series.values() for v in vals.values()])
