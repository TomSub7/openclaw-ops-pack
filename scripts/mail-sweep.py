#!/usr/bin/env python3
"""Read-only Gmail sweep for configured keywords via Composio (mcporter CLI).

Never sends mail. Fetches recent messages from one or more Composio-connected
Gmail accounts, filters locally by keyword, and reports hits as JSON or a
short text block. Tracks already-reported message ids in a state file so
repeat runs don't re-alert.

Config (env vars, see ops-pack.env.example):
  OPS_MAIL_ACCOUNTS   "label=composio_account_id,label2=..." (required)
  OPS_KEYWORDS_FILE   path to a keyword list, one per line (optional)
  OPS_STATE_DIR       where the seen-message-id state file lives (optional)

Usage:
  mail-sweep.py [--hours N] [--accounts label1,label2] [--json | --text]
                 [--state PATH] [--dry-run]

Exit codes: 0 no hits, 10 hits found, 2 tool/auth/config error.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_KEYWORDS = ["overdue", "invoice", "final notice", "urgent", "past due"]


def load_accounts():
    raw = os.environ.get("OPS_MAIL_ACCOUNTS", "")
    accounts = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        label, account_id = pair.split("=", 1)
        accounts[label.strip()] = account_id.strip()
    return accounts


def load_keywords():
    kw_file = Path(os.environ.get("OPS_KEYWORDS_FILE", "")) if os.environ.get("OPS_KEYWORDS_FILE") else None
    if kw_file and kw_file.exists():
        lines = kw_file.read_text().splitlines()
        kws = [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]
        if kws:
            return kws
    return DEFAULT_KEYWORDS


def default_state_path():
    state_dir = Path(os.environ.get("OPS_STATE_DIR", str(Path.home() / ".openclaw" / "state")))
    return state_dir / "mail-sweep-seen.json"


def load_state(path):
    if path.exists():
        try:
            return set(json.loads(path.read_text()).get("seen", []))
        except (json.JSONDecodeError, OSError):
            return set()
    return set()


def save_state(path, seen):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"seen": sorted(seen)}, indent=2))


def fetch_account(account_id, hours):
    """Call GMAIL_FETCH_EMAILS via mcporter/Composio. Returns list of message dicts."""
    days = max(1, -(-hours // 24))  # ceil; Gmail's newer_than has no hour unit
    # ponytail: Composio truncates responses above ~25 messages into "data_preview";
    # page in 25s with page_token, stop at 200 messages or when older than the window.
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    out, page_token = [], None
    while True:
        args = {"user_id": "me", "query": f"newer_than:{days}d", "max_results": 25,
                "include_payload": False, "verbose": False}
        if page_token:
            args["page_token"] = page_token
        tools = [{"tool_slug": "GMAIL_FETCH_EMAILS", "arguments": args, "account": account_id}]
        call = ("composio.COMPOSIO_MULTI_EXECUTE_TOOL(tools:" + json.dumps(tools)
                + ", sync_response_to_workbench:false)")
        proc = subprocess.run(["mcporter", "call", call], capture_output=True, text=True, timeout=90)
        if proc.returncode != 0:
            raise RuntimeError(f"mcporter exit {proc.returncode}: {proc.stderr.strip()[:500]}")
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"non-JSON mcporter output: {e}: {proc.stdout[:300]}")
        if payload.get("error"):
            raise RuntimeError(f"composio error: {payload['error']}")
        results = payload.get("data", {}).get("results", [])
        resp = results[0].get("response", {}) if results else {}
        if not resp.get("successful") or "data" not in resp:
            raise RuntimeError(f"GMAIL_FETCH_EMAILS unsuccessful or truncated: {json.dumps(resp)[:400]}")
        msgs = resp["data"].get("messages", [])
        out.extend(msgs)
        page_token = resp["data"].get("nextPageToken")
        oldest = None
        for m in msgs:
            try:
                oldest = datetime.fromisoformat(m.get("messageTimestamp", "").replace("Z", "+00:00"))
            except ValueError:
                pass
        if not page_token or len(out) >= 200 or (oldest and oldest < cutoff):
            break
    return out


def matches(msg, keyword_patterns):
    # ponytail: word-boundary match, not substring, to avoid false hits on short keywords.
    haystack = " ".join(
        [msg.get("subject", ""), msg.get("sender", ""), msg.get("preview", {}).get("body", "")]
    )
    return [kw for kw, pattern in keyword_patterns if pattern.search(haystack)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=3)
    ap.add_argument("--accounts", default="all")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--text", action="store_true")
    ap.add_argument("--state", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    accounts = load_accounts()
    if not accounts:
        print("OPS_MAIL_ACCOUNTS not set, see ops-pack.env.example", file=sys.stderr)
        return 2

    account_names = list(accounts) if args.accounts == "all" else args.accounts.split(",")
    bad = [a for a in account_names if a not in accounts]
    if bad:
        print(f"unknown account label(s): {bad}, choose from {list(accounts)}", file=sys.stderr)
        return 2

    keywords = load_keywords()
    keyword_patterns = [(kw, re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE)) for kw in keywords]
    cutoff = datetime.now(timezone.utc) - timedelta(hours=args.hours)
    state_path = args.state or default_state_path()
    seen = load_state(state_path)

    hits = []
    for name in account_names:
        account_id = accounts[name]
        try:
            messages = fetch_account(account_id, args.hours)
        except (RuntimeError, subprocess.TimeoutExpired, OSError) as e:
            print(f"fetch failed for {name} ({account_id}): {e}", file=sys.stderr)
            return 2
        for msg in messages:
            ts_raw = msg.get("messageTimestamp", "")
            try:
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            except ValueError:
                continue
            if ts < cutoff:
                continue
            msg_id = msg.get("messageId", "")
            if msg_id in seen:
                continue
            kw_hit = matches(msg, keyword_patterns)
            if not kw_hit:
                continue
            hits.append({
                "account": name,
                "id": msg_id,
                "date": ts_raw,
                "from": msg.get("sender", ""),
                "subject": msg.get("subject", ""),
                "snippet": msg.get("preview", {}).get("body", "")[:200],
                "keywords_hit": kw_hit,
            })

    hits.sort(key=lambda h: h["date"], reverse=True)

    if not args.dry_run and hits:
        seen.update(h["id"] for h in hits)
        save_state(state_path, seen)

    if args.text:
        if not hits:
            print("no hits")
        else:
            lines = []
            for h in hits:
                dt = datetime.fromisoformat(h["date"].replace("Z", "+00:00"))
                lines.append(f"[{h['account']}] {dt:%d.%m %H:%M} | {h['keywords_hit'][0]} | {h['subject']}")
            print("\n".join(lines)[:900])
    else:
        print(json.dumps(hits, indent=2))

    return 10 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
