"""Turn build findings into GitHub issues (run inside GitHub Actions; uses the gh CLI).

  python scripts/report_issues.py attention   # new sources that need a person
  python scripts/report_issues.py failure     # the weekly build failed

One open issue per title: if it already exists, a comment is added instead of a
duplicate. DECISIONS D-043.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

FRESHNESS = Path(__file__).resolve().parent.parent / "data" / "samples" / "freshness.json"
FOOTER = "\n\n---\n_Opened automatically by the polyview build._"


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def upsert(title: str, body: str, label: str) -> None:
    existing = json.loads(gh("issue", "list", "--state", "open", "--search", f'in:title "{title}"',
                             "--json", "number,title"))
    match = next((i for i in existing if i["title"] == title), None)
    if match:
        gh("issue", "comment", str(match["number"]), "--body", body + FOOTER)
        print(f"commented on #{match['number']}: {title}")
    else:
        try:
            gh("label", "create", label, "--force", "--color", "C5DEF5")
        except subprocess.CalledProcessError:
            pass
        gh("issue", "create", "--title", title, "--body", body + FOOTER, "--label", label)
        print(f"opened: {title}")


def attention() -> None:
    report = json.loads(FRESHNESS.read_text())
    items, errors = report.get("attention", []), report.get("errors", [])
    for item in items:
        upsert(f"New source needs wiring in: {item['what']}",
               f"**Source:** {item['source']}\n\n**What:** {item['what']}\n\n**To do:** {item['action']}",
               "data-update")
    if errors:
        upsert("Source discovery had errors",
               "The weekly check for new source files couldn't reach some sites. The build used the "
               "files it already knew about.\n\n" + "\n".join(f"- {e}" for e in errors), "data-update")
    if not items and not errors:
        print("nothing needs attention")


def failure() -> None:
    upsert("Weekly site build failed",
           "The site build failed, so the live site still shows the last successful build.\n\n"
           f"Run: {os.environ.get('RUN_URL', '(unknown)')}\n\n"
           "Common causes: a state website was down, a file layout changed, or a reconciliation "
           "check (`python -m ingest checks`) is out of tolerance.", "build-failure")


if __name__ == "__main__":
    {"attention": attention, "failure": failure}[sys.argv[1]]()
