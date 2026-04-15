# Completion — MBP sync (warrior_bot_v2 + warrior_manual)

**Author:** CC (Opus)
**Date:** 2026-04-15 late evening
**Directive:** `2026-04-15_directive_mbp_sync.md`
**Status:** Part 1 (warrior_manual) is **Case D — stopped, awaiting Manny's call.** Part 2 (warrior_bot_v2 main) ready to copy-paste.

---

## Part 1 — warrior_manual state on Mac mini

### Branching decision: **Case D**

Folder `~/warrior_manual/` exists and has real contents, but is not a git repo.

**Git state:**
```
remote -v        → fatal: not a git repository
status           → fatal: not a git repository
log              → fatal: not a git repository
branch           → fatal: not a git repository
```

**Folder contents** (mostly up-to-date, actively used):
```
manual_trader.py       33,795 B   Apr 14 14:03
ui.py                   9,611 B   Apr 14 13:40
executor.py             9,693 B   Apr 14 13:47
config.py               2,597 B   Apr 14 13:43
position_manager.py     3,091 B   Apr 12 20:23
logger.py               2,167 B   Apr 14 13:16
alerts.py               1,090 B   Apr 12 20:23
requirements.txt          52 B   Apr 12 20:22
CLAUDE.md              2,840 B   Apr 12 20:25
.env                     967 B   Apr 14 13:14     ← don't cross machines
.env.example           1,183 B   Apr 12 20:59     ← OK to commit
venv/                   (local)                    ← don't commit
logs/                   (runtime)                  ← don't commit
__pycache__/            (build)                    ← don't commit
```

The original `2026-04-12_directive_warrior_manual.md` was executed (files exist, Manny's been iterating), but `git init` was never run. The tool has been living as a loose directory.

### What I did NOT do (per directive rule)

- Did NOT run `git init`.
- Did NOT create a GitHub repo.
- Did NOT push anything.

Per directive: "Do not create a GitHub remote without Manny's explicit approval."

### What needs Manny's call

One decision: where should the warrior_manual remote live?

- **Option 1** — new private repo under `mannyluke4` (or whichever account hosts `warrior_bot`). Clean separation. Name: `warrior_manual`.
- **Option 2** — a sub-repo / monorepo arrangement inside the existing `warrior_bot` repo. Probably not what we want since the manual tool is separate scope.
- **Option 3** — another owner (org, etc.).

Once you OK one, the Mac mini side is ~30 seconds of commands. MBP clone happens after push.

---

## Part 2 — warrior_bot_v2 main state

### Origin check — no local commits waiting on main

```
git fetch origin       → fetched cleanly
git log origin/main..main → (empty)
```

Local `main` is **not ahead** of `origin/main`. Nothing sitting locally that should have been pushed. The session-resume + BIRD autopsy + directive work from today is all on `v2-ibkr-migration` (unmerged, per directive rule).

### Origin/main tip

```
8e6b4e9 Add scanner RVOL/ADV diagnostics, PM_HOD_GATE flag, directives, cowork reports, and backtest state
625197c Update IBKR directive: add Phase 0 (preserve V1), remove day estimates
28bee64 DIRECTIVE: Full IBKR migration — gut Alpaca, rebuild scanner pipeline, prune 6K lines + 200 env vars
1d97d5c Full system audit: scanner pipeline rebuild recommended, 259 env vars, 3 scanners with zero parity
4fdf57b ADV parity investigation: both scanners wrong in different directions
```

`8e6b4e9` is what MBP will fetch.

---

## Part 3 — Commands for Manny to run on MBP

### warrior_bot_v2 update (ready now — no blockers)

```bash
cd ~/warrior_bot_v2
git fetch origin
git checkout main
git pull origin main
```

Expected end state: `main` at `8e6b4e9`. The session-resume branch (`v2-ibkr-migration`) is deliberately excluded per your "latest stable only" direction. If you later want it on the MBP for viewing, that's a separate `git fetch origin v2-ibkr-migration` + `git checkout v2-ibkr-migration`.

### warrior_manual clone (blocked until Part 1 is resolved)

Once a remote is created (after your OK), the MBP commands will be:

```bash
cd ~
git clone <remote-url> warrior_manual
cd warrior_manual
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# Copy or create .env from .env.example
cp .env.example .env
# then fill in API keys manually
```

---

## Gotchas to flag for MBP setup

Not blockers, but heads-ups for when Manny sets up on the MBP:

1. **`.env` does not cross machines.** The `.env` on Mac mini has Alpaca/IBKR keys that are machine-specific (or at minimum should be re-verified before live use on a second machine). MBP will need its own `.env` created from `.env.example`.

2. **venv is Mac-mini-specific.** Python wheels compiled for mini's Python version + architecture. MBP needs a fresh `python3 -m venv venv && pip install -r requirements.txt`. Verify Python version match with `python3 --version` on both sides — if MBP is on a different Python (e.g., 3.11 vs 3.12), no issue, but worth noting.

3. **IBKR clientId conflicts if both machines connect to the same Gateway.** If you plan to run warrior_manual on MBP AND the auto-bot on Mac mini, they need different `clientId` values in the IBKR connect call. Current Mac mini auto-bot uses whatever is in its code — I didn't dig into this since the directive said "Does not resolve Mac mini / MBP clientId coordination." Flagging for when you tackle it.

4. **Tailscale / Gateway tunnel (Phase 2 of the original warrior_manual directive).** The original `2026-04-12_directive_warrior_manual.md` mentioned Phase 2 as tunneling MBP → Mac mini Gateway. Not set up yet. If you want manual bot on MBP to connect to the Mac mini Gateway, this is the next piece. Separate scope from today's directive.

5. **`__pycache__/` on Mac mini warrior_manual.** When we eventually `git init` + push, make sure `.gitignore` excludes `__pycache__/`, `venv/`, `logs/`, and `.env`. Standard Python gitignore. Will handle at commit time once you OK the remote.

---

## Awaiting Manny

One decision: OK to create a private GitHub repo `mannyluke4/warrior_manual` (or alt name/location) and push the existing Mac mini files? If yes, I'll:

1. `git init` in `~/warrior_manual`
2. Write a proper `.gitignore` (excludes `venv/`, `__pycache__/`, `.env`, `logs/`)
3. `git add .` + initial commit
4. `gh repo create mannyluke4/warrior_manual --private --source=. --push` (or push to whatever URL you specify)
5. Report the URL

Then append the MBP clone commands to this file with the real remote.

---

*CC (Opus). Files are there and current — just not yet a repo. One decision needed.*
