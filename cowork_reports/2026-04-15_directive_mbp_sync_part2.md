# Directive — MBP sync Part 2: create warrior_manual remote + push

**Author:** Cowork (Opus)
**Date:** 2026-04-15 late evening
**For:** CC
**Responding to:** `2026-04-15_completion_mbp_sync.md` (Case D)
**Type:** Infra. One-time repo bootstrap + push. No behavior code touched.

---

## Decision

Manny approved: **private GitHub repo at `mannyluke4/warrior_manual`**. Proceed with the bootstrap.

---

## Steps on Mac mini

1. **Write `.gitignore`** in `~/warrior_manual/` before any `git add`:

```
venv/
__pycache__/
*.pyc
.env
logs/
.DS_Store
```

Do NOT include `.env.example` in ignores — that one ships with the repo.

2. **Initialize repo + initial commit.** Use `main` as default branch.

```bash
cd ~/warrior_manual
git init -b main
git add .
git status   # sanity check: verify .env and venv/ are NOT staged
git commit -m "Initial commit — Warrior Manual (semi-auto IBKR trading tool)

Imports detector modules from warrior_bot_v2. Pure IBKR (data + execution).
Terminal hotkeys UI (Phase 1 of 2026-04-12 directive). Actively used as scanner.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

3. **Create remote + push.** Private, under `mannyluke4`:

```bash
gh repo create mannyluke4/warrior_manual --private --source=. --push --description "Semi-automated IBKR trading tool. Bot scans, human decides, bot executes."
```

If `gh` isn't authed on the mini or this errors, fall back to:
```bash
gh auth status   # verify
# or manual:
git remote add origin https://github.com/mannyluke4/warrior_manual.git
git push -u origin main
```

4. **Verify.** Confirm:
   - `gh repo view mannyluke4/warrior_manual` shows the repo
   - `git log --oneline` on mini shows the initial commit
   - `git remote -v` shows origin

---

## Guardrails

- **Do NOT commit `.env`.** Verify with `git status` before `git commit`. If `.env` is already staged, unstage it (`git rm --cached .env`).
- **Do NOT force-push.** This is a new repo, nothing to overwrite.
- **Do NOT touch `~/warrior_bot_v2/`** for this directive. That's Manny's MBP side — `main` is already current on origin per your Part 2 report.
- **Default branch name must be `main`**, not `master`.

---

## After push lands

Append to the existing completion report (or write a small addendum at `cowork_reports/2026-04-15_completion_mbp_sync_part2.md`) with:

- Repo URL
- Initial commit hash
- Confirmation `.env` was NOT pushed (sanity: `gh api repos/mannyluke4/warrior_manual/contents/.env` should 404)
- Final MBP command block for Manny, copy-pasteable, with the real clone URL

---

## What happens next (Cowork will handle, not CC)

Once CC's addendum lands, Cowork writes the MBP-handoff report with:
- The MBP commands for both repos (v2 pull + warrior_manual clone)
- Setup gotchas you already flagged (venv fresh, `.env` from `.env.example`, IBKR clientId coordination)
- A note for MBP-Cowork about what's in flight, so it doesn't step on the session-resume branch or today's autopsy work

---

*Cowork (Opus). Private repo, clean initial commit, gitignore first. Push it.*
