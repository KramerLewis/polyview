"""State agency payments ("Open Checkbook") from fiscal.wa.gov.

One workbook per biennium, one sheet per fiscal year, columns:
Bien, FY, FMonth, Agy, Agency, Object, Category, Subobj, SubCategory, Vendor, Amount.

Note: no fund or program columns, so this shows *who was paid* but cannot by
itself be compared to fund-level appropriations. See docs/sources.md.
"""

from __future__ import annotations

from collections import defaultdict

import openpyxl

from .common import SAMPLES, fetch, write_csv

URL = "https://fiscal.wa.gov/Spending/VendorPayments{suffix}.xlsx"
BIENNIA = {"2025-27": "2527"}


def run() -> None:
    for biennium, suffix in BIENNIA.items():
        path = fetch(URL.format(suffix=suffix), "vendor_payments", f"VendorPayments{suffix}.xlsx")
        wb = openpyxl.load_workbook(path, read_only=True)
        by_agency_object: dict[tuple, float] = defaultdict(float)
        n = 0
        for ws in wb.worksheets:
            rows = ws.iter_rows(values_only=True)
            header = [str(h).strip() for h in next(rows)]
            idx = {h: i for i, h in enumerate(header)}
            for r in rows:
                if r[idx["Amount"]] is None:
                    continue
                key = (str(r[idx["Bien"]]).strip(), str(r[idx["FY"]]).strip(),
                       str(r[idx["Agy"]]).strip(), str(r[idx["Agency"]]).strip(),
                       str(r[idx["Object"]]).strip(), str(r[idx["Category"]]).strip())
                by_agency_object[key] += float(r[idx["Amount"]])
                n += 1
        rows_out = [
            {"biennium": k[0], "fiscal_year": k[1], "agency_code": k[2], "agency": k[3],
             "object": k[4], "category": k[5], "amount": round(v, 2)}
            for k, v in sorted(by_agency_object.items())
        ]
        write_csv(SAMPLES / f"vendor_payments_by_agency_object_{suffix}.csv", rows_out)
        print(f"vendor payments {biennium}: {n:,} payment rows, "
              f"${sum(by_agency_object.values()):,.0f} total, {len(rows_out)} agency/object rows")
