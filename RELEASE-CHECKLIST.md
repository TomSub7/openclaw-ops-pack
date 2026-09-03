# Release checklist: openclaw-ops-pack

Private repo staged: https://github.com/TomSub7/openclaw-ops-pack
Gates run and passing as of 2026-09-03 (sanitisation, syntax, em-dash, install test, jobs.sh --dry-run). Nothing below runs until you approve the release for this lane.

## 1. Flip the repo public

```bash
gh repo edit TomSub7/openclaw-ops-pack --visibility public
```

This is the only irreversible-feeling step (repo becomes world-readable). Confirm the sanitisation grep is still clean immediately before running it:

```bash
cd ~/Projects/openclaw-ops-pack
grep -rniE 'tomas|1482277767|5bbb668|cfat_|marty' scripts/ install.sh jobs.sh || echo clean
git log --oneline -5
```

## 2. Publish on skills.sh

Seller entity for the listing: **Bureao Flow GmbH**.

1. Go to skills.sh, sign in with the GmbH's account.
2. New listing, point at `https://github.com/TomSub7/openclaw-ops-pack` (must be public first, step 1).
3. Copy the listing body from `LISTING-skills-sh.md` in this repo.
4. Free listing, no payment fields on skills.sh itself.

## 3. Create the Gumroad product (GmbH account)

Seller entity: **Bureao Flow GmbH**. Log into Gumroad under the GmbH's account, not a personal one.

Fields:

| Field | Value |
|---|---|
| Product name | OpenClaw Ops Pack |
| Price | EUR 29 (one-time) |
| Type | Digital product (zip or GitHub link gate) |
| Content | Attach a zip of this repo, or a private-repo-invite delivery if Gumroad supports it |
| Description | Copy from `LISTING-gumroad.md` in this repo |
| Seller / business name | Bureao Flow GmbH |
| Cover / thumbnail | none shipped, add one before going live or leave default |

**VAT note (German GmbH selling digital goods to EU consumers).** Digital products sold B2C across EU borders fall under the EU's One-Stop-Shop (OSS) VAT scheme, not German VAT alone: Bureao Flow GmbH must charge the VAT rate of the buyer's country, not Germany's, and remit it centrally through Germany's OSS portal (BZSt) rather than registering in every buyer country. Gumroad acts as a marketplace facilitator in many jurisdictions and may collect/remit VAT itself depending on Gumroad's own OSS registration and the buyer's location; confirm Gumroad's merchant-of-record status for the GmbH's account before assuming no OSS filing is needed on the GmbH side. State this plainly to the seller before the product goes live: OSS applies, check Gumroad's MoR terms, do not assume EUR 29 is VAT-inclusive without checking.

## 4. Rollback

If anything is wrong post-publish (leaked token, wrong entity, wrong price):

```bash
gh repo edit TomSub7/openclaw-ops-pack --visibility private
```

Then pull the Gumroad and skills.sh listings manually (both have a delete/unpublish action in their own dashboards; no API wired here).

## Gate summary (run before FIRE, again right before flipping public)

| Gate | Command | Expect |
|---|---|---|
| Sanitisation | `grep -rniE 'tomas\|1482277767\|5bbb668\|cfat_\|marty' scripts/ install.sh jobs.sh` | no output (exit 1) |
| Shell syntax | `bash -n install.sh jobs.sh scripts/*.sh` | no output, exit 0 |
| Python syntax | `python3 -m py_compile scripts/*.py` | exit 0 |
| Em-dash | `grep -rn $'\xe2\x80\x94' *.md` | no output (exit 1) |
| Install path | `HOME=$(mktemp -d) bash install.sh` | "copied 7 scripts", exit 0 |
| Jobs dry-run | `bash jobs.sh --dry-run \| grep -c '^openclaw cron add'` | 6 |
| Repo visibility | `gh repo view TomSub7/openclaw-ops-pack --json visibility -q .visibility` | PRIVATE until FIRE, PUBLIC after step 1 |
