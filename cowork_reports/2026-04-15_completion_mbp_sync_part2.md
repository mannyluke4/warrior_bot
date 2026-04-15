# Completion — MBP sync Part 2 (warrior_manual bootstrap + push)

**Author:** CC (Opus)
**Date:** 2026-04-15 late evening
**Directive:** `2026-04-15_directive_mbp_sync_part2.md`
**Status:** Shipped. Repo live at https://github.com/mannyluke4/warrior_manual (private).

---

## What landed

- **Repo URL:** https://github.com/mannyluke4/warrior_manual (private, under `mannyluke4`)
- **Initial commit:** `4ba8be2` on `main`
  - `"Initial commit — Warrior Manual (semi-auto IBKR trading tool)"`
  - 11 files: `.env.example`, `.gitignore`, `CLAUDE.md`, `alerts.py`, `config.py`, `executor.py`, `logger.py`, `manual_trader.py`, `position_manager.py`, `requirements.txt`, `ui.py`
- **`.gitignore`:** `venv/`, `__pycache__/`, `*.pyc`, `.env`, `logs/`, `.DS_Store`
- **Description:** "Semi-automated IBKR trading tool. Bot scans, human decides, bot executes."

## Secrets check — clean

Verified via GitHub API that `.env` was NOT pushed:

```
gh api repos/mannyluke4/warrior_manual/contents/.env
→ {"message":"Not Found","status":"404"}
```

And that `.env.example` was pushed (intentional — it's the placeholder template):

```
gh api repos/mannyluke4/warrior_manual/contents/.env.example
→ "name":".env.example"
```

No credential leaks.

## Along the way — two small infra changes

Not code behavior changes; flagging for the record:

1. **Installed `gh` CLI on Mac mini.** It wasn't present. `brew install gh` via Homebrew at `/opt/homebrew/bin/gh`, version `2.89.0`. One-time install.
2. **Authenticated `gh` as `mannyluke4`** (web browser flow, Manny at keyboard). Confirmed via `gh auth status` — logged in, HTTPS protocol, keyring-stored token.

Both are persistent on the mini. Any future `gh` operations from this machine work without re-authing.

---

## Final copy-paste block for Manny on MBP

Run these in order on the MacBook Pro:

### 1. Update warrior_bot_v2 main (stable branch only)

```bash
cd ~/warrior_bot_v2
git fetch origin
git checkout main
git pull origin main
# Expected end state: main at 8e6b4e9 (or later if new main commits land between now and then)
```

If `~/warrior_bot_v2` doesn't exist on MBP yet (first-time clone):

```bash
cd ~
git clone https://github.com/mannyluke4/warrior_bot.git warrior_bot_v2
cd warrior_bot_v2
git checkout main
```

### 2. Clone warrior_manual (new repo)

```bash
cd ~
gh repo clone mannyluke4/warrior_manual
# or equivalently:
# git clone https://github.com/mannyluke4/warrior_manual.git
cd warrior_manual
```

### 3. Set up warrior_manual venv + deps on MBP

```bash
cd ~/warrior_manual
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Create MBP `.env`

`.env` is NOT in the repo (correctly). Create from the template and fill in your keys:

```bash
cp .env.example .env
# then edit .env with the MBP's API keys (Alpaca, IBKR, FMP, etc.)
# use your preferred editor — the repo's .env is machine-local forever
```

---

## Gotchas still worth flagging (same as Part 1, repeated for MBP context)

1. **`.env` is per-machine.** Don't copy from mini — re-fill on MBP. If you're using the same Alpaca paper keys across machines, they'll work, but IBKR clientId must differ.

2. **IBKR clientId conflicts.** If MBP's warrior_manual and mini's warrior_bot_v2 both connect to the same IBKR Gateway simultaneously, they need different `clientId` integers in the connect call. Manual inspection of `manual_trader.py` connect config (around line-wherever `ib.connect(...)` is) will show what MBP's using. Match it against bot_v3_hybrid.py's clientId and make sure they differ.

3. **Tailscale / cross-machine Gateway.** Not set up yet. If you want MBP's warrior_manual to reach the Mac mini's IBKR Gateway (per Phase 2 of the original warrior_manual directive), that's a separate Cowork-on-MBP directive.

4. **Python version match.** Check `python3 --version` on both sides. Wheels in `requirements.txt` should work on any modern 3.11+, but worth verifying.

5. **Session-resume branch.** `v2-ibkr-migration` on warrior_bot_v2 contains today's in-flight work (session resume, BIRD autopsy, dynamic SQ attempts prototype). It's deliberately NOT merged to main. If MBP-Cowork wants to view it, `git fetch origin v2-ibkr-migration && git checkout v2-ibkr-migration`. Do not merge from MBP — integration happens from this machine after review.

---

## Verify after MBP setup

```bash
# On MBP, from ~/warrior_manual after setup:
source venv/bin/activate
python -c "import manual_trader; print('import OK')"
```

If that succeeds, the tool is ready to run. Launching it (terminal UI) is Manny's call — the directive here was just to get the code there.

---

## Handoff note for MBP-Cowork

Three in-flight items on `warrior_bot_v2:v2-ibkr-migration` that MBP-Cowork should know about before making any changes:

- **Session resume (7 commits, 080baf2 → 033fb57).** Full crash-recovery feature. Gated OFF default. Validated end-to-end via crash-injection on the Mac mini. Don't touch the write-point wiring or the resume-mode path.
- **BIRD autopsy (9687b47) + three follow-up directives (sim1981 fix `89e52c5`, dynamic SQ attempts `4708a7a`, YTD re-run in flight).** Dynamic SQ attempts is the prototype; Phase 3 YTD validation blocks on a scanner_results regeneration currently running in background. Don't stage or commit changes to `squeeze_detector.py` / `squeeze_detector_v2.py` / `simulate.py` on MBP side until those reports land.
- **Scanner_results is being regenerated** for all 49 YTD dates via `scanner_sim.py --date <each>`. In progress as of this writing (~5 of 49 done, ETA ~2 hours). When it's done I'll kick off the YTD re-batch here on the mini; no MBP action needed.

---

*CC (Opus). Repo lives. Secrets clean. MBP commands ready.*
