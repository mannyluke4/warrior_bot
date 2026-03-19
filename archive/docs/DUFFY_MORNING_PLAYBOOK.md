# Duffy Morning Routine — Live Scanner Playbook

## Schedule (All Times Eastern)

| Time (ET) | Time (MT) | Action |
|-----------|-----------|--------|
| 6:15 AM | 4:15 AM | Boot up, verify systems |
| 6:30 AM | 4:30 AM | Start live scanner |
| 7:00 AM | 5:00 AM | Review initial candidate list |
| 7:00-7:14 AM | 5:00-5:14 AM | Monitor scanner, finalize watchlist |
| 7:14 AM | 5:14 AM | Lock watchlist — no more additions |
| 7:15 AM | 5:15 AM | Confirm bot has watchlist loaded, stand by |

## Step 1 — System Check (6:15 AM ET)

Before anything else, verify everything is running:

1. **Bot process**: Confirm the warrior bot is running in the VM
2. **IBKR connection**: Confirm the bot has an active IBKR connection
3. **Databento key**: Confirm `DATABENTO_API_KEY` is set in `.env`
4. **FMP key**: Confirm `FMP_API_KEY` is set in `.env`
5. **Network**: Confirm the VM can reach `live.databento.com` and `financialmodelingprep.com`

If anything is down, fix it before proceeding. Do NOT start the scanner with a broken bot.

## Step 2 — Start Live Scanner (6:30 AM ET)

Run the live scanner:
```bash
cd /Users/mannyluke/warrior_bot
source venv/bin/activate
python live_scanner.py
```

The scanner will:
- Fetch yesterday's close prices from Databento (EQUS.SUMMARY)
- Connect to the live EQUS.MINI feed
- Begin streaming pre-market data for all US equities
- Calculate gap percentages in real-time

Monitor the console output for errors. If the Databento connection fails, check API key and network.

## Step 3 — Review Candidates (7:00 AM ET)

By 7:00 AM ET, the scanner should have an initial candidate list. Review what's been flagged.

**For each candidate, the scanner has already applied these filters automatically:**
- Profile A: float 0.5M-5M, price $3-$10, gap 10-40%
- Profile B: top 1-2 only, float 5-50M, price $3-$10, gap 10-25%

**Duffy's manual sanity check (quick, not deep research):**
- Does the symbol look real? (not an ETN, leveraged product, or warrant)
- Is the gap driven by news? (catalyst = good; random spike with no volume = skip)
- Is pre-market volume meaningful? (a few hundred shares on a gap = suspect)

If a candidate looks wrong, don't add it. When in doubt, skip it.

## Step 4 — Update Watchlist (7:00-7:14 AM ET)

Add approved candidates to the bot's watchlist. The live scanner should handle this automatically, but verify:

1. Check the bot's active watchlist matches what the scanner output
2. Profile A candidates go first — these are the primary trades
3. Profile B candidates go second — max 1-2 of these
4. Total watchlist should be **5-8 stocks max**

If the scanner found more than 8 qualifying candidates, prioritize by:
1. Highest pre-market volume (liquidity = tradeable)
2. Gap in the 15-25% range (sweet spot from backtest)
3. Float in the 1-3M range (where CANF and WATT lived)

## Step 5 — Lock Watchlist (7:14 AM ET)

At exactly 7:14 AM ET, the watchlist is **LOCKED**. No more additions after this point.

- Stop monitoring the scanner for new candidates
- The bot takes over from here — it will score and trade based on its own logic
- Duffy's job is done until post-session review

## What Duffy Does NOT Do

- **Do not** add stocks after 7:14 AM ET
- **Do not** remove stocks from the watchlist once added (the bot handles skip logic)
- **Do not** interfere with the bot's trading decisions
- **Do not** manually adjust position sizes or stop losses
- **Do not** call Claude Code during the morning routine (save credits)

## Troubleshooting

**Scanner won't connect to Databento:**
- Check `DATABENTO_API_KEY` in `.env`
- Check VM firewall allows `live.databento.com`
- Try: `python -c "import databento as db; print(db.Historical().metadata.list_datasets())"`

**FMP float lookup failing:**
- Check `FMP_API_KEY` in `.env`
- Free tier = 250 calls/day, should be plenty
- Float cache (`scanner_results/float_cache.json`) reduces API calls

**Scanner finds zero candidates:**
- This can happen on slow market days — not every day has gap-ups
- Verify the scanner is actually receiving data (check console output)
- If truly no candidates: skip the day, no watchlist update needed

**Bot doesn't see the watchlist:**
- Check the watchlist file/config the bot reads from
- Verify the scanner wrote to the correct location
- Restart the bot if needed to pick up the new watchlist

## Fallback — Manual Mode

If the live scanner is broken and can't be fixed by 7:00 AM ET:
1. Open the Warrior Trading scanner manually (browser)
2. Watch for gap-up stocks in the 7:00-7:14 window
3. Apply the filter rules by hand (Profile A: float 0.5-5M, price $3-$10, gap 10-40%)
4. Manually update the bot's watchlist

This is the same process Luke has been doing. The live scanner just automates it.

## Post-Session (Optional)

After market close, save the day's scanner output for future analysis:
- `scanner_results/live_YYYY-MM-DD.json` (candidates found)
- `scanner_results/live_YYYY-MM-DD.log` (scanner activity log)
- Note any candidates that were added but the bot chose not to trade (good data for filter refinement)

## Credit Awareness

This morning routine does NOT use Claude Code or OpenRouter. The scanner is a standalone Python script. Duffy can run this entire playbook by himself without burning API credits. Only escalate to Claude Code if something is broken and needs a code fix.
