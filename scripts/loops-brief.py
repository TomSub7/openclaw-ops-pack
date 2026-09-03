#!/usr/bin/env python3
"""Read-only brief: open-loops register + outbox tracker + a ledger file.
Stdlib only. Prints TOP LOOPS / DUE 7D / LEDGER <date>, under 1200 chars. --json for structured output.

Config (env vars, see ops-pack.env.example): OPS_REGISTER_FILE, OPS_TRACKER_FILE,
OPS_LEDGER_FILE. Any of the three left unset just skips that section.

Expected shapes (all optional, missing file = empty section):
  register: a markdown table with rank "1".."5" in the first column, loop text in
            the second, next-action text in the sixth.
  tracker:  a markdown table where the sixth column holds a date (or date-ish
            text) to alert on if it falls within the next 7 days.
  ledger:   a markdown doc with "## <text with a YYYY-MM-DD date>" section
            headings; the brief reads the most recent section's near-term lines.
"""
import os
import re
import sys
import json
import argparse
from pathlib import Path
from datetime import date, timedelta

REGISTER = Path(os.environ["OPS_REGISTER_FILE"]) if os.environ.get("OPS_REGISTER_FILE") else None
TRACKER = Path(os.environ["OPS_TRACKER_FILE"]) if os.environ.get("OPS_TRACKER_FILE") else None
LEDGER = Path(os.environ["OPS_LEDGER_FILE"]) if os.environ.get("OPS_LEDGER_FILE") else None

# order matters: ISO first, then DD.MM.YYYY / DD/MM/YYYY, then bare DD.MM / DD/MM (year filled in by caller)
DATE_RE = re.compile(
    r'\b(\d{4})-(\d{2})-(\d{2})\b'
    r'|\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b'
    r'|\b(\d{1,2})[./](\d{1,2})\b(?!\d)'
)


def parse_dates(text, year_hint, today):
    out = []
    for m in DATE_RE.finditer(text):
        try:
            if m.group(1):
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            elif m.group(4):
                d, mo, y = int(m.group(4)), int(m.group(5)), int(m.group(6))
            else:
                d, mo, y = int(m.group(7)), int(m.group(8)), year_hint
            dt = date(y, mo, d)
        except ValueError:
            continue
        # bare DD.MM with no year: if it lands far in the past, it's probably next year
        if m.group(1) is None and m.group(4) is None and dt < today - timedelta(days=200):
            dt = dt.replace(year=dt.year + 1)
        out.append(dt)
    return out


def trunc(s, n):
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def table_rows(text, first_cell_re):
    """Yield list-of-cells for '| a | b | ... |' lines whose first cell matches first_cell_re."""
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells and first_cell_re.match(cells[0]):
            yield cells


def get_register_rows():
    if not REGISTER or not REGISTER.exists():
        return []
    text = REGISTER.read_text(encoding="utf-8")
    rows = list(table_rows(text, re.compile(r"^[1-5]$")))
    top = [r for r in rows if r[0] in ("1", "2")]
    if not top:
        top = rows[:5]
    return top


def get_tracker_due(today):
    if not TRACKER or not TRACKER.exists():
        return []
    text = TRACKER.read_text(encoding="utf-8")
    rows = list(table_rows(text, re.compile(r".+")))
    due = []
    for r in rows:
        if len(r) < 6:
            continue
        if r[0].lower() in ("sent", "submitted") or set(r[0]) == {"-"}:
            continue  # header / separator
        row_text = " | ".join(r)
        if "closed" in row_text.lower():
            continue
        escalate = r[5]
        dates = parse_dates(escalate, today.year, today)
        if any(today - timedelta(days=1) <= d <= today + timedelta(days=7) for d in dates):
            due.append({"box": r[1], "to": r[2], "ask": r[3], "escalate": escalate})
    return due


def get_ledger_brief(today):
    if not LEDGER or not LEDGER.exists():
        return None, []
    text = LEDGER.read_text(encoding="utf-8")
    lines = text.splitlines()
    heading_idx = [
        i for i, l in enumerate(lines)
        if l.startswith("## ") and re.search(r"\d{4}-\d{2}-\d{2}", l)
    ]
    if not heading_idx:
        return None, []
    last = heading_idx[-1]
    heading = lines[last][3:]
    end = len(lines)
    for i in range(last + 1, len(lines)):
        if lines[i].startswith("## "):
            end = i
            break
    body = lines[last + 1:end]
    near = []
    for l in body:
        if not l.strip():
            continue
        dates = parse_dates(l, today.year, today)
        if any(today <= d <= today + timedelta(days=14) for d in dates):
            near.append(l.lstrip("- ").strip())
    return heading, near


def build_brief():
    today = date.today()
    top_loops = get_register_rows()
    due = get_tracker_due(today)
    heading, ledger_lines = get_ledger_brief(today)

    result = {
        "top_loops": [
            {"rank": r[0], "loop": r[1], "next_action": r[5] if len(r) > 5 else ""}
            for r in top_loops[:5]
        ],
        "due_7d": due[:6],
        "ledger_heading": heading,
        "ledger_near_term": ledger_lines[:3],
    }
    return result


def render_text(result):
    out = ["TOP LOOPS"]
    for item in result["top_loops"]:
        out.append(f"[R{item['rank']}] {trunc(item['loop'], 70)} -> {trunc(item['next_action'], 55)}")
    if not result["top_loops"]:
        out.append("none")

    out.append("")
    out.append("DUE 7D")
    for item in result["due_7d"]:
        out.append(f"{trunc(item['escalate'], 45)} | {trunc(item['to'], 25)}: {trunc(item['ask'], 35)}")
    if not result["due_7d"]:
        out.append("none")

    out.append("")
    heading = result["ledger_heading"] or "none"
    out.append(f"LEDGER {trunc(heading, 90)}")
    for l in result["ledger_near_term"]:
        out.append(f"- {trunc(l, 100)}")

    text = "\n".join(out)
    if len(text) > 1200:
        text = text[:1130].rsplit("\n", 1)[0] + "\n..."
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    result = build_brief()
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(render_text(result))


if __name__ == "__main__":
    main()
