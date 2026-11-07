"""Run ingesters: ``python -m ingest [budget_bills legislature vendor_payments districts]``."""

import sys

from . import budget_bills, districts, legislature, vendor_payments

INGESTERS = {
    "budget_bills": budget_bills.run,
    "legislature": legislature.run,
    "vendor_payments": vendor_payments.run,
    "districts": districts.run,
}

if __name__ == "__main__":
    names = sys.argv[1:] or list(INGESTERS)
    for name in names:
        if name not in INGESTERS:
            sys.exit(f"unknown ingester {name!r}; choose from {', '.join(INGESTERS)}")
        print(f"== {name}")
        INGESTERS[name]()
