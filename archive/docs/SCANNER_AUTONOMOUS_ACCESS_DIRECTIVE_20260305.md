# Autonomous Scanner Access — Research Directive
**Date:** 2026-03-05  
**Prepared by:** Duffy  
**For:** Perplexity — research and solution design  
**Priority:** CRITICAL — blocking full autonomous operation

---

## Goal

Duffy (running in Lima VM `lima-duffy` on Luke's MacBook Pro) needs to autonomously read live stock data from the Warrior Trading scanner **without any manual action from Luke**. This is the final blocker before Duffy can run the full pre-market routine independently:

1. Wake up at 4:50 AM MT
2. Read the live scanner
3. Classify stocks through the profile decision tree
4. Write qualifying stocks to `watchlist.txt`
5. Start `bot.py`
6. Monitor and update watchlist throughout the session

---

## Environment

- **Duffy's runtime:** Lima VM (`lima-duffy`), Linux 6.8.0 arm64 on macOS M-series MacBook Pro
- **Host machine:** macOS (mannyluke's MacBook Pro)
- **Scanner URL:** `https://chatroom.warriortrading.com/dashboard?hash=...&page=Alert&userId=190294&sourceCode=WT&roomId=scanner-Momo&mainId=B36C&popout=false`
- **Scanner architecture:** React SPA, data delivered via Socket.IO from `scan-prod.warriortrading.com`
- **No scanner API exists** — data only available via browser automation or direct Socket.IO connection
- **Cloudflare protection** on chatroom subdomain — blocks headless browsers

## What's Already Been Tried (Failed)

| Approach | Why It Failed |
|---|---|
| agent-browser (headless Chromium) | Cloudflare fingerprints HeadlessChrome UA, serves 437-byte stub |
| playwright-extra + stealth | navigator.webdriver=false but binary still detected |
| CDP + SSH reverse tunnel (-R flag) | Lima VM: setsockopt TCP_NODELAY errors, port unreachable |
| cloudflared tunnel | trycloudflare.com not on VM approved endpoint list |
| Manual Chrome + CDP | Works but requires Luke to launch Chrome manually each session — not autonomous |

---

## Two Solutions to Research

---

### Solution A: Persistent Chrome via macOS launchd (Near-Term, Practical)

**Concept:** Configure a macOS launchd plist that automatically launches Chrome with `--remote-debugging-port=9222` at login. Chrome runs persistently in the background, always open to the scanner URL. Duffy connects to it via CDP whenever needed. Zero manual steps after initial setup.

**Why this works:**
- Real Chrome = Cloudflare never blocks it
- launchd = Chrome restarts automatically if it crashes
- CDP over TCP to `192.168.5.2:9222` from inside VM (Lima host IP, TCP works even though ICMP/ping fails — known Lima networking quirk)
- Luke logs in once, session is preserved in `--user-data-dir`

**Questions for Perplexity:**

**Q1: launchd plist for persistent Chrome**
Write the exact `~/Library/LaunchAgents/com.warriorbot.chrome.plist` content that:
- Launches Chrome at login with `--remote-debugging-port=9222 --user-data-dir="$HOME/.chrome-duffy"`
- Keeps it running (KeepAlive = true)
- Opens to `https://chatroom.warriortrading.com/...` (the scanner URL)
- Doesn't interfere with Luke's normal Chrome (different user-data-dir)

**Q2: CDP connection from Lima VM**
Confirm: from inside a Lima VM, can Playwright/Node.js connect to `http://192.168.5.2:9222` (the host Mac's CDP port) reliably? Is there any Lima VZ networking config needed? Previous SSH reverse tunnel failed with TCP_NODELAY errors — does direct TCP to host IP work differently?

**Q3: Session persistence across reboots**
Chrome's `--user-data-dir="$HOME/.chrome-duffy"` stores cookies and session state. If the Mac reboots and Chrome auto-relaunches via launchd, will the Warrior Trading session cookie still be valid? Or does the scanner require re-authentication on each browser launch? If re-auth is needed, is there a way to automate it (e.g., saved password + Chrome auto-fill)?

**Q4: Scanner data extraction via CDP**
Once connected to the scanner tab via CDP (using Node.js `playwright` with `connectOverCDP`), what is the most reliable way to extract scanner entries? Options:
- A) DOM scraping (read the table rows directly)
- B) Intercept Socket.IO messages via `Page.setRequestInterception` or Network events
- C) `Page.evaluate()` to access the React component state directly

Which approach is most reliable for a real-time polling loop (checking every 15-30 seconds)?

---

### Solution B: Socket.IO Direct Authentication (Long-Term, Fully Headless)

**Concept:** Authenticate programmatically with just Luke's Warrior Trading username/password to obtain a JWT, then connect directly to `scan-prod.warriortrading.com` via Socket.IO. No browser. Duffy runs a Node.js process inside the VM that maintains a persistent Socket.IO connection to the scanner data stream.

**Known auth flow (from reverse-engineering the SPA):**
```
URL hash (SSO token) → GET /beta/sso?data={hash} → JWT → Socket.IO connection to scan-prod.warriortrading.com
```

The hash in the URL is time-limited/single-use, which is why we can't just hardcode it. But there may be a way to get a fresh JWT programmatically from credentials.

**Questions for Perplexity:**

**Q5: Can we get a JWT from username/password?**
The Warrior Trading chatroom app uses a hash-based SSO flow. Is there a direct credential → JWT endpoint that bypasses the hash? Standard OAuth2/username-password flows sometimes exist alongside SSO flows.

Specifically: when a user logs into `warriortrading.com` main site, what auth token is issued? Is that token usable to authenticate against `chatroom.warriortrading.com` and ultimately get a `scan-prod.warriortrading.com` JWT?

**Q6: Socket.IO connection details**
From the JS bundle (`main.2a3d291f.js`), we know:
- Scanner connects to `https://scan-prod.warriortrading.com`
- Uses Socket.IO with events: `join`, `joinResult`, subscribed channel events
- Requires Bearer JWT in the connection headers

What is the complete Node.js `socket.io-client` connection sequence to subscribe to scanner alerts? Include the exact event names and payload structure for joining the scanner room.

**Q7: Rate limits and connection stability**
If Duffy maintains a persistent Socket.IO connection to `scan-prod.warriortrading.com` throughout the trading session (7:00 AM - 12:00 PM ET daily), are there known rate limits, reconnect requirements, or session expiry issues to handle? What's the recommended reconnect strategy?

---

## Implementation Priority

| Solution | Effort | Time to Implement | Reliability | Autonomous? |
|---|---|---|---|---|
| **A: launchd + CDP** | Low | Today (hours) | High | ✅ (after initial login) |
| **B: Socket.IO direct** | High | Days-weeks | Very High | ✅ (fully headless) |

**Recommend:** Implement Solution A today as the immediate fix. Pursue Solution B as the long-term replacement. Both can coexist — A as fallback if B's auth ever breaks.

---

## Scanner Data Format (for reference)

When stocks appear on the scanner, the data we need to extract:
- **Ticker symbol** (e.g., JZXN)
- **Float / shares outstanding** (e.g., 1.32M)
- **Gap %** (e.g., +57%)
- **Strategy type** (e.g., "Former Momo Stock", "Squeeze Alert - Up 10% in 10min")
- **Time of appearance** (ET timestamp)

This is used to run the profile decision tree:
- Float <5M + 7:00-7:14 AM ET → Profile A
- Float 5-50M + 7:00-7:14 AM ET → Profile B
- Everything else → SKIP

---

## Approved Endpoints (VM Network Policy)

Already approved (relevant ones):
- `*.warriortrading.com` ✅
- `scan-prod.warriortrading.com` (need to confirm — part of `*.warriortrading.com`)
- `192.168.5.2` (Lima host IP — local subnet, not filtered)

Not yet approved (may be needed):
- npm registry (for installing playwright) — `registry.npmjs.org`

---

*Report by Duffy — 2026-03-05*  
*Context: BROWSER_ACCESS_ISSUE_REPORT.md (full prior attempt history)*
