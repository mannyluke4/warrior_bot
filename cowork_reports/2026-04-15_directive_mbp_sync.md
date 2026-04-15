# Directive — MBP sync: v3 hybrid (main) + warrior_manual

**Author:** Cowork (Opus)
**Date:** 2026-04-15 late evening
**For:** CC
**Type:** Infra / machine sync. No code changes to behavior.
**Why:** Manny wants the MacBook Pro current. He's actively using Warrior Manual as a scanner (superb at finding the right stocks) and wants to keep iterating on it from the MBP via Cowork over there. He'll do his real trading through TradingView; the manual tool is the scanner layer.

---

## Goal

Two repos, both current on the MBP:

1. **`~/warrior_bot_v2/`** → updated to `origin/main` (latest stable only — do NOT merge `v2-ibkr-migration` in).
2. **`~/warrior_manual/`** → current working copy, pulled down to MBP and ready to run.

---

## Part 1 — warrior_manual status check

Run on Mac mini:

```bash
cd ~/warrior_manual
git remote -v
git status
git log --oneline -5
git branch --show-current
```

Report all four outputs.

### Branching decision tree

Based on what you find:

**Case A — has remote and remote is current:** Nothing to do on the Mac mini side. MBP just needs to `git clone <remote>`.

**Case B — has remote but Mac mini is ahead of remote:** `git push` whatever branch is current, then report push result.

**Case C — is a git repo but no remote:** Stop. Do not create a GitHub repo without Manny's say-so. Report the state and wait. Most likely we'll create a private GitHub repo under Manny's account and push.

**Case D — not a git repo at all:** Stop. Report. Same path: needs `git init` + remote + push, but Manny decides on the remote first.

**Case E — folder doesn't exist:** Stop. Report. That would mean the 2026-04-12 directive never got executed, which is worth knowing.

If Case C or D, and Manny gives you the go-ahead (he may do so in-line before you finish), create the repo private under his GitHub and push. Default branch name `main`.

---

## Part 2 — warrior_bot_v2 update on MBP

Once we know the warrior_manual story, the MBP steps. Manny is on the MBP running Cowork there to execute these — write them out cleanly for him.

Expected commands for Manny to run on MBP:

```bash
cd ~/warrior_bot_v2
git fetch origin
git checkout main
git pull origin main
```

Then for warrior_manual (once Case A/B is resolved):

```bash
cd ~
git clone <remote-url> warrior_manual
# OR if already cloned:
# cd ~/warrior_manual && git pull
```

### Follow-up for MBP warrior_manual

After clone, Manny will need:
- Python venv setup + dependencies installed (`requirements.txt` if it exists)
- IBKR Gateway config on MBP if he wants to run it there (or Tailscale-tunnel to Mac mini Gateway per the Phase 2 mention in the original `2026-04-12_directive_warrior_manual.md`)

**Don't script the MBP-side IBKR setup in this directive.** That's Cowork-on-MBP territory. This directive's job is to get the code there.

---

## Part 3 — Deliverable

Short report at `cowork_reports/2026-04-15_completion_mbp_sync.md` with:

1. warrior_manual state report (remote, branch, last 5 commits, any push that was needed).
2. Confirmation `warrior_bot_v2` main is up to date on origin (no pending commits sitting locally that should have been pushed).
3. The exact commands Manny should run on the MBP, copy-pasteable.
4. Any setup gotchas flagged (Python version mismatch, missing `.env`, IBKR clientId conflicts if both machines connect, etc.).

---

## Hard rules

- **Do NOT merge `v2-ibkr-migration` into `main`.** Manny explicitly chose "latest stable (merge to main)" meaning only what's already there. The in-flight session-resume work stays on its branch.
- **Do NOT create a GitHub remote without Manny's explicit approval** if warrior_manual doesn't have one.
- **Do NOT touch `.env` files.** They don't cross machines.
- **Zero code changes** to any behavior-affecting file. This is infra plumbing only.

---

## What this does NOT do

- Does not set up IBKR Gateway on the MBP.
- Does not configure Tailscale or cross-machine gateway access.
- Does not modify either repo's code.
- Does not resolve Mac mini / MBP clientId coordination — that's a separate concern if Manny wants to run the manual bot from the MBP and the auto-bot keeps running on the Mac mini.

---

*Cowork (Opus). Get the files to the right place first. MBP setup comes next.*
