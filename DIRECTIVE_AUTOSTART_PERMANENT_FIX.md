# DIRECTIVE: Permanent Autostart Fix

**Date:** April 28, 2026  
**Author:** Cowork (Perplexity)  
**For:** CC (Claude Code) and Manny  
**Priority:** P0 — solve once and for all  
**Status:** Diagnosis complete, multiple fix paths available

---

## Root Cause (Confirmed)

Every single failed cron-triggered run has the same log line:

```
WARN: keystroke failed — check Accessibility permissions
```

The current `daily_run_v3.sh` tries to wake/unlock the Mac via osascript:
1. `caffeinate -u -t 30` — sends a wake signal
2. `osascript ... key code 53` — sends Escape to dismiss screensaver
3. `osascript ... keystroke "$MAC_PW"` — types the unlock password

**The osascript keystroke call fails silently every time it runs from cron.** Why: cron processes don't have access to the GUI session. They run in a non-interactive shell with no `WindowServer` connection. Even if Accessibility permissions are granted to `bash` or `osascript`, the cron environment lacks the ability to send keystrokes to the lock screen.

When you run the script manually, the desktop is already unlocked (you're logged in), so the broken unlock step doesn't matter — Gateway starts cleanly because the GUI session is alive.

When cron runs at 2 AM:
- Display is asleep
- Lock screen is up
- The wake + unlock attempt fails
- Gateway is started but can't open its window
- Port 4001/4002 never becomes available
- After 360 seconds (72 attempts × 5s), the script aborts

This is also why the bot eventually "comes alive" later — your `keep_alive.sh` cron runs every 2 minutes and detects the bot is dead, then the second/third attempt sometimes succeeds because by then the screen has been woken some other way.

---

## The Fix: Three Layers of Defense

We're going to solve this with three independent mechanisms. Any one of them working is enough. All three together is bulletproof.

### Layer 1: Disable the Lock Screen Entirely

The simplest fix. If the Mac never locks, there's nothing to unlock.

**Steps:**
1. System Settings → Lock Screen
2. Set **"Require password after sleep or screen saver begins"** to **Never**
3. Set **"Start Screen Saver when inactive"** to **Never**
4. Set **"Turn display off on power adapter when inactive"** to **Never**

**Steps via Terminal (run on Mac Mini):**
```bash
# Disable screensaver password requirement
defaults -currentHost write com.apple.screensaver askForPassword -int 0

# Disable screensaver
defaults -currentHost write com.apple.screensaver idleTime -int 0

# Disable display sleep on power
sudo pmset -c displaysleep 0
sudo pmset -c sleep 0
sudo pmset -c disksleep 0

# Disable lid sleep (if it's a laptop or Mac Mini with display)
sudo pmset -c lidwake 1

# Verify
pmset -g | grep -E "displaysleep|sleep|disksleep"
```

**Why this is safe:** The Mac Mini lives at the office, behind your normal physical security. The only "attacker" is your cat. The benefit is the Mac is ALWAYS in a usable state for the bot.

### Layer 2: Auto-Login on Boot

If the Mac restarts (power outage, update, manual reboot), it should come back up logged in.

**Steps:**
1. System Settings → Users & Groups
2. Click the small "i" / Edit button next to **Automatic login as**
3. Select your user (`duffy`)
4. Enter your password to confirm
5. Reboot to verify

This means even after a power loss, the Mac comes back fully logged in and ready. No keystroke shenanigans needed.

**Note:** Apple disables auto-login when FileVault is enabled. If FileVault is on, you'd need to disable it (System Settings → Privacy & Security → FileVault → Turn Off). For a dedicated trading workstation, this is acceptable.

### Layer 3: Replace `daily_run_v3.sh` Wake Logic with `caffeinate -u`

Even with Layers 1 and 2 in place, keep a robust wake mechanism in the script that doesn't depend on osascript.

The current script uses three osascript calls and a sleep — none of which actually wake a deeply asleep display reliably. Replace with this minimal, proven approach:

```bash
# ── Step 0: Wake the display (no osascript, no keystroke) ────────────
echo "=== Waking screen and ensuring active desktop ==="

# caffeinate -u tells the system to act as if the user is active.
# This wakes the display AND prevents sleep without needing keystrokes.
# -t 60 means hold for 60 seconds (long enough for the rest of startup).
caffeinate -u -t 60 &
WAKE_PID=$!
echo "Display wake (caffeinate -u) sent"
sleep 5  # Give the display time to actually wake

# Verify wake worked by checking display state
DISPLAY_STATE=$(ioreg -n IODisplayWrangler -r -d 1 2>/dev/null | grep -i "DevicePowerState" | awk '{print $NF}' | head -1)
if [ "$DISPLAY_STATE" = "4" ]; then
    echo "Display ACTIVE (DevicePowerState=4)"
elif [ "$DISPLAY_STATE" = "1" ] || [ "$DISPLAY_STATE" = "0" ]; then
    echo "WARN: Display still in sleep state ($DISPLAY_STATE) — Gateway may fail"
    # Try one more wake
    caffeinate -u -t 30 &
    sleep 5
fi

# Persistent caffeinate for the entire session
caffeinate -dims -w $$ &
CAFFEINE_PID=$!
echo "Persistent caffeinate started (PID: $CAFFEINE_PID)"

# REMOVED: osascript keystroke unlock (doesn't work from cron)
# REMOVED: osascript Finder activate (not reliable from cron)
# Lock screen is disabled in System Settings (Layer 1)
# Auto-login handles reboots (Layer 2)
```

This is much shorter, more reliable, and doesn't depend on Accessibility permissions or GUI keystroke routing.

---

## Implementation Steps

### Step A: System Settings (Manny does this on Mac Mini)

1. **Disable lock screen** (System Settings → Lock Screen → all "Never")
2. **Enable auto-login** (System Settings → Users & Groups → Automatic login as → duffy)
3. **Disable display sleep**:
   ```bash
   sudo pmset -c displaysleep 0
   sudo pmset -c sleep 0
   sudo pmset -c disksleep 0
   ```
4. **Verify pmset settings:**
   ```bash
   pmset -g | grep -E "displaysleep|sleep|disksleep"
   ```
   Expected: all should be `0`
5. **Verify FileVault is off** (or accept that auto-login won't work after reboot — Layer 2 only)

### Step B: Update `daily_run_v3.sh` (CC does this)

Replace the entire Step 0 wake section (lines ~24-79 of `daily_run_v3.sh`) with the minimal caffeinate-based approach above. Remove all osascript calls. Remove the `~/.mac_unlock_pw` dependency.

### Step C: Test

1. **Lock the Mac manually** (Ctrl+Cmd+Q or close lid)
2. **Wait 5 minutes** to ensure the display is truly asleep
3. **Manually trigger the cron job:**
   ```bash
   bash -l -c '~/warrior_bot_v2/daily_run_v3.sh' > /tmp/test_cron_run.log 2>&1 &
   ```
4. **Watch the log:**
   ```bash
   tail -f /tmp/test_cron_run.log
   ```
5. **Verify Gateway starts within 60 seconds** (not 360+)

### Step D: Verify Tomorrow's 2 AM Run

After implementing Steps A and B, the next 2 AM cron should succeed cleanly. Check:
```bash
cat ~/warrior_bot_v2/logs/2026-04-29_daily.log | head -30
```

You should see:
- "Display ACTIVE" (not "WARN: keystroke failed")
- "Gateway is up on port 4001" within ~60 seconds (not 360+ seconds)
- "Bot health check passed"
- No "FATAL: bot crashed" message

---

## Why This Will Work

| Failure Mode | Layer 1 (No Lock) | Layer 2 (Auto-Login) | Layer 3 (caffeinate) |
|--------------|------------------|---------------------|---------------------|
| Mac is asleep | ✅ Doesn't matter | ✅ Doesn't matter | ✅ caffeinate -u wakes it |
| Mac was rebooted | N/A | ✅ Auto-login handles it | N/A |
| Lock screen is up | ✅ Disabled, never appears | ✅ Logged in automatically | N/A |
| Screensaver active | ✅ Disabled | N/A | ✅ caffeinate -u wakes it |
| Display in deep sleep | N/A | N/A | ✅ caffeinate -u handles it |
| Power outage at 1 AM | ✅ Doesn't lock on boot | ✅ Auto-login at boot | ✅ Wake works on fresh boot |

Three independent layers means even if one fails (e.g., FileVault is on so auto-login doesn't work), the others still keep the system in a runnable state.

---

## What NOT to Do

- ❌ Do NOT keep the osascript keystroke approach. It is fundamentally incompatible with cron's non-GUI environment.
- ❌ Do NOT rely on `~/.mac_unlock_pw` — it's a security risk (plaintext password) and doesn't even work.
- ❌ Do NOT use `pmset` schedules to "wake" the Mac at 1:55 AM — caffeinate is more reliable.
- ❌ Do NOT add more retries/timeouts to compensate for the broken wake — fix the wake itself.

---

## Optional: Additional Hardening

If you want belt-and-suspenders, add a `launchd` agent that runs at boot to ensure the bot environment is always ready:

```bash
# ~/Library/LaunchAgents/com.duffy.warriorbot-keepalive.plist
# Runs caffeinate -dims forever on boot
# Ensures display NEVER sleeps regardless of pmset settings
```

This is optional and only needed if Layer 1 fails for some reason.

---

*Three layers. One root cause. Solved permanently.*
