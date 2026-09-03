# skills.sh listing: openclaw-ops-pack

## Name
openclaw-ops-pack

## One-line summary
Six scheduled OpenClaw jobs: hourly mail sweep, daily loops brief, calendar
prep, ledger diff, weekly research, nightly Cloudflare credit burn check.

## Category
Automation / scheduling

## Price
Free (MIT license)

## Description

Most OpenClaw setups only respond when you talk to them. This pack adds a
proactive layer: six jobs on a schedule, each one a read-only script plus a
short agent instruction, each one ending in a gate (an exit code, a hit
count, a changed-file count) so the job never gets to claim "done" on a
guess.

Install with `./install.sh`, fill in one env file, run `./jobs.sh` with your
Telegram chat id, done. Every script is documented, standalone, and runs
under any scheduler, not only OpenClaw's own cron.

Nothing here sends mail, posts anything public, or moves money. The only
output channel is a Telegram message to a chat id you configure.

## Tags
openclaw, cron, automation, telegram, cloudflare, workers-ai, scheduling,
proactive-agent

## Links
Repo: (fill in on publish)
License: MIT

## Seller
Published and supported by Bureao Flow GmbH (brand BureauFlow, bureauflow.io), Trier, Germany. Support: the contact page on bureauflow.io.
