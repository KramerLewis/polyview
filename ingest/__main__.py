"""Run ingesters: ``python -m ingest [name ...]`` (all when no names are given)."""

import sys

from . import budget_bills, budget_current, checks, outlook, budget_to_actual, budget_to_actual_detail, districts, legislature, vendor_payments

INGESTERS = {
    "budget_bills": budget_bills.run,
    "budget_current": budget_current.run,  # needs budget_bills first
    "checks": checks.run,  # reconcile against published totals; needs budget_bills
    "budget_to_actual": budget_to_actual.run,
    "budget_to_actual_detail": budget_to_actual_detail.run,
    "legislature": legislature.run,
    "outlook": outlook.run,
    "vendor_payments": vendor_payments.run,
    "districts": districts.run,
}

if __name__ == "__main__":
    names = sys.argv[1:] or list(INGESTERS)
    for name in names:
        if name not in INGESTERS:
            sys.exit(f"unknown ingester {name!r}; choose from {', '.join(INGESTERS)}")
        print(f"== {name}")
        if INGESTERS[name]() is False:
            sys.exit(f"{name} failed")
