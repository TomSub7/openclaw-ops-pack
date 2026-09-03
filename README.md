# openclaw-ops-pack

A proactive job pack for OpenClaw on Cloudflare Workers AI: hourly mail sweep,
daily loops brief, calendar prep, ledger diff, weekly research, nightly credit
burn. Every job ends with a runnable gate, so a scheduled agent never gets to
claim "done" without proof: an exit code, a hit count, a changed-file count.

None of this touches a live mailbox for writes. Every script here is
read-only against your own data; the only thing that leaves your machine is a
Telegram message you configure the destination for.

## What is in the box

| Script | What it does |
|---|---|
| `scripts/mail-sweep.py` | Sweeps one or more Composio-connected Gmail accounts for keyword hits, tracks seen message ids so it never re-alerts. |
| `scripts/loops-brief.py` | Reads a task register, an outbox tracker, and a ledger file, prints a 3-section brief under 1200 characters. |
| `scripts/calendar-next.sh` | Lists Calendar.app events for the next N days, any calendar except the ones you exclude. |
| `scripts/ledger-diff.sh` | Snapshots a set of watched files daily and prints what changed since the last run. |
| `scripts/cf-cost-tracker.sh` | Pulls Cloudflare Worker request cost and Workers AI neuron burn via the GraphQL analytics API, trips a threshold, optionally posts a Telegram line. |
| `scripts/council.py` | Sends a draft or a decision to several models through a Cloudflare AI Gateway in parallel, returns a consensus verdict instead of one model's opinion. |
| `scripts/telegram-send.sh` | Stateless Telegram send wrapper: truncates to the API limit, retries once on rate limit, logs every send. |

All six of the scheduled jobs (`jobs.sh`) call these scripts and nothing else.
No script sends mail, posts anything public, or spends money on its own.

## Requirements

- macOS (calendar-next.sh uses AppleScript via osascript; the rest is
  cross-platform Python 3 / bash + curl + jq).
- Python 3.9+, no third-party packages, standard library only.
- `jq` for `cf-cost-tracker.sh`.
- [OpenClaw](https://github.com) installed and configured, for the cron
  scheduling in `jobs.sh`. The scripts themselves run standalone from any
  cron, launchd, or systemd timer if you would rather not use OpenClaw's
  scheduler; only `jobs.sh` is OpenClaw-specific.
- A Telegram bot token, if you want the Telegram delivery path (optional,
  every script degrades gracefully without it, except telegram-send.sh
  itself).
- A Composio account with a connected Gmail integration, only if you use
  `mail-sweep.py`.
- A Cloudflare account with Workers AI and an AI Gateway, only if you use
  `cf-cost-tracker.sh` or `council.py`.

## 5-minute install

```bash
git clone <this repo> && cd openclaw-ops-pack
./install.sh                       # copies scripts to ~/.openclaw/scripts,
                                    # writes ~/.openclaw/ops-pack.env from the example
$EDITOR ~/.openclaw/ops-pack.env   # fill in your paths, accounts, tokens
source ~/.openclaw/ops-pack.env
python3 ~/.openclaw/scripts/loops-brief.py   # sanity check with no cron yet
```

Then, once OpenClaw itself is configured and you know your Telegram chat id:

```bash
CHAT_ID=123456789 ./jobs.sh
```

This creates the 6 cron jobs. Edit `jobs.sh` first if you want different
schedules, models, or job messages; it is a plain shell script, not a
template engine.

## Config reference

See `ops-pack.env.example` for every variable, with inline comments. Copy it
to `~/.openclaw/ops-pack.env`, edit, and source it wherever these scripts
run (a shell profile, a cron wrapper, or your scheduler's env block).

Keyword list for the mail sweep: copy `keywords.example.txt` to the path in
`OPS_KEYWORDS_FILE` and edit it for your own creditors, deadlines, and
contacts. One keyword per line, matched as a whole word, case-insensitive.

## Screenshots

(placeholder: a terminal capture of `loops-brief.py`'s output, and a Telegram
screenshot of a `[MAIL]` alert, go here before publishing)

## Pricing

Core pack: free, published to skills.sh. If you want a maintained "pro pack"
with the multi-model `council.py` reviewer and the `cf-cost-tracker.sh` credit
burn tracker pre-wired to a second scheduler (so you are not dependent on one
tool), that is EUR 29 one-time on Gumroad. The free core has everything you
need to run all 6 jobs; the pro pack is for people who want the adjudication
and cost-guard layer without wiring it themselves.

## FAQ

**Does this send anything on its own?** No. Every script is read plus a
single Telegram message you control the destination for. Nothing posts to a
mailbox, a form, or a public surface.

**Does this work without OpenClaw?** Yes for the scripts. `jobs.sh` calls
`openclaw cron add`, so the scheduling layer is OpenClaw-specific; point any
other scheduler at the scripts directly and you lose nothing but the
one-command setup.

**What if I only want one or two jobs?** Run `install.sh`, then call
`openclaw cron add` (or your own scheduler) for just the ones you want,
using `jobs.sh` as the template.

## License

MIT, see `LICENSE`.

## Seller
Published and supported by Bureao Flow GmbH (brand BureauFlow, bureauflow.io), Trier, Germany. Support: the contact page on bureauflow.io.
