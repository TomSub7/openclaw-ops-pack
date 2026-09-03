# Gumroad listing: openclaw-ops-pack (pro)

## Title
OpenClaw Ops Pack, pro: council reviewer + credit burn tracker

## Price
EUR 29, one-time

## Three bullets
- Six scheduled OpenClaw jobs, wired and ready: mail sweep, daily brief, calendar prep, file diff, weekly research, nightly cost check.
- A multi-model council script that sends any draft or decision to several AI vendors in parallel and returns one consensus verdict instead of a single model's guess.
- A Cloudflare credit burn tracker that trips a threshold and pages you before a runaway job spends your budget.

## Description

The free core pack (skills.sh) gives you all 6 jobs and every script. This
pro pack adds two things people keep asking to wire up themselves: a
multi-vendor "council" reviewer for anything you are about to send or decide,
and a nightly Cloudflare cost tracker that actually pages you before a
budget trips, not after.

Every job in this pack ends with a runnable gate: an exit code, a hit count,
a changed-file count. Nothing claims "done" on a hunch. Nothing sends mail,
posts anything public, or spends money without you having already wired the
one delivery channel (Telegram) it reports through.

## What is included

- All 6 job scripts and `jobs.sh` to create the cron entries in one command.
- `council.py`, multi-model draft and decision review over a Cloudflare AI
  Gateway (Gemini, DeepSeek, Llama, Granite, NVIDIA Nemotron, whichever keys
  you have).
- `cf-cost-tracker.sh`, GraphQL-based Workers AI neuron and Worker request
  cost tracking, pace-to-budget math, Telegram alert on trip.
- `ops-pack.env.example` and `keywords.example.txt`, fully commented.

## Requirements

macOS for the calendar job (AppleScript). Everything else runs anywhere
Python 3.9+ and bash are available. OpenClaw for the scheduler; the scripts
themselves run standalone under any cron.

## FAQ

**Is this a subscription?** No, one-time purchase.

**Do I need Cloudflare?** Only for `cf-cost-tracker.sh` and `council.py`. The
other four jobs need no Cloudflare account at all.

**Can I see the code before buying?** Yes, the core pack (all 6 jobs, no
council or cost tracker) is free and open source on skills.sh and GitHub.

## Seller
Published and supported by Bureao Flow GmbH (brand BureauFlow, bureauflow.io), Trier, Germany. Support: the contact page on bureauflow.io.
