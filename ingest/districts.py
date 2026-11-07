"""Legislative district boundaries (Census TIGER/Line, state 53 = Washington).

Washington uses the same 49 districts for both chambers, so the SLDU (upper)
file is sufficient; SLDL is fetched for completeness. The shapefiles stay in
data/raw (not committed). Converting to GeoJSON/PMTiles for the web map is a
Phase 2 task.

Caveat: districts were redrawn in 2012 and 2022, and a federal court ordered
changes in the Yakima Valley in 2024. Confirm which map each TIGER vintage
reflects before attributing historic spending to districts.
"""

from __future__ import annotations

from .common import fetch

TIGER = "https://www2.census.gov/geo/tiger/TIGER{year}/{layer}/tl_{year}_53_{lower}.zip"


def run(year: int = 2025) -> None:
    for layer in ("SLDU", "SLDL"):
        url = TIGER.format(year=year, layer=layer, lower=layer.lower())
        path = fetch(url, "districts", f"tl_{year}_53_{layer.lower()}.zip")
        print(f"{layer} {year}: {path.stat().st_size:,} bytes")
