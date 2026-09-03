---
name: openclaw-ops-pack
description: Install a proactive job pack for OpenClaw on Cloudflare Workers AI. Six scheduled jobs, hourly mail sweep, daily loops brief, calendar prep, ledger diff, weekly research, nightly credit burn. Use when the user wants OpenClaw running scheduled background checks instead of only replying when asked.
---

# openclaw-ops-pack

This skill installs six scheduled OpenClaw jobs plus the read-only scripts
that back them. Nothing in the pack sends mail, posts anything public, or
spends money without a human already having approved the delivery channel
(Telegram) it reports through.

## When to use this

The user wants OpenClaw to check things on a schedule and report in, rather
than only responding to direct messages: a mail sweep for keywords, a daily
brief of open tasks, calendar prep, a diff on files that matter, a weekly
research scan, and a nightly cost check against a Cloudflare credit budget.

## Steps

1. Run `./install.sh` from this pack's root. It copies every script in
   `scripts/` to `~/.openclaw/scripts` and writes `~/.openclaw/ops-pack.env`
   from the example if it does not already exist.
2. Have the user fill in `~/.openclaw/ops-pack.env`: their watched files,
   Composio account ids, Telegram bot token and chat id, and (optionally)
   Cloudflare account id and API token.
3. Copy `keywords.example.txt` to the path named in `OPS_KEYWORDS_FILE` and
   edit it to the user's own creditors, deadlines, and VIP contacts.
4. Confirm the env loads: `source ~/.openclaw/ops-pack.env && python3
   ~/.openclaw/scripts/loops-brief.py` should run without error (it prints
   "none" for any section whose file is not configured yet).
5. Run `CHAT_ID=<their chat id> ./jobs.sh` to create the 6 cron jobs. Ask for
   their Telegram chat id first if you do not have it; do not guess it.
6. Read `openclaw cron list` back to the user and confirm all 6 jobs are
   present and enabled before calling this done.

## What this does not do

It never fires an external send, form submission, or public post on its own.
The `--announce` delivery on each job only reaches the Telegram chat id the
user supplied in step 2, and that is a report, not an action taken on their
behalf. If the user wants a job that takes an external action, that is a
different, higher-stakes skill; do not extend this pack's jobs to do it
without a separate explicit ask.

## Seller
Published and supported by Bureao Flow GmbH (brand BureauFlow, bureauflow.io), Trier, Germany. Support: the contact page on bureauflow.io.
