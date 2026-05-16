# Framework Planning — Kickoff

**Date:** 2026-05-17
**Author:** Cowork (Perplexity)
**For:** Manny + CC
**Trigger:** Manny corrected my pacing: "CC can do the work of 100 skilled men's 1 week load in under an hour. Why wait a whole month when we can build it now and use the next 30 days to test and refine?"
**Status:** Planning phase active. 5 research workstreams running in parallel.

---

## Locked-in decisions from tonight

1. **Wider portfolio.** Not VP + Box only. Build the framework with 4-6 strategies from day one, plug-in architecture for adding more.
2. **Wider universe.** Not small-cap-gappers. "Higher prices fluctuate better" — drop the small-cap-only constraint. Universe filtered on liquidity + level-structure quality, not premarket gap.
3. **Multi-timeframe.** Levels from daily/yesterday's profile + intraday updates, confirmation on 1m bars. Best of both.
4. **Bot stays autonomous.** No manual trading lane.
5. **Pacing:** plan deeply, build in parallel, test exhaustively. Don't wait — but don't skip planning.

---

## The framing correction I needed

I kept assuming human-time pacing: "weeks for the design doc, weeks for the build." Wrong. CC works at agent speed. The constraint isn't engineering hours — it's **planning quality and data validation.**

The right cycle:
1. **Plan deeply** through research and architecture work
2. **Build in parallel** — CC can run multiple agents on different components
3. **Test exhaustively** with backtest + paper before any real money
4. **Adjust based on data** — never assume what works

The 3-week WB failure wasn't because we lacked time. It was because we built the wrong primitive without enough planning. The fix isn't more building time. It's **rigorous planning so the building targets the right thing.**

---

## Five research workstreams now running

| Topic | Why it matters | Output |
|---|---|---|
| **VP & Market Profile** — mathematical foundations | The video's methodology has 40+ years of literature. Extract what's rigorous vs marketing. | `/home/user/workspace/research_vp_market_profile.md` |
| **Universe selection** — operationalize "higher prices fluctuate better" | Need rigorous criteria for the new universe. ADV thresholds, spread quality, day-range profiles. | `/home/user/workspace/research_universe_selection.md` |
| **Multi-strategy architecture** — patterns from production systems | Strategy registry, A/B testing, capital allocation, concurrency. Don't reinvent. | `/home/user/workspace/research_multi_strategy_architecture.md` |
| **Candidate strategies** — portfolio of 5-10 strategies that fit the framework | Map each strategy to (level_source, arrival, confirmation, stop, target). Rank by edge, bot-shape, complexity. | `/home/user/workspace/research_candidate_strategies.md` |
| **Backtest infrastructure** — multi-strategy, multi-timeframe backtest with VP support | Validate strategies BEFORE live paper. What's needed beyond `simulate.py` today. | `/home/user/workspace/research_backtest_infrastructure.md` |

All running in parallel. Outputs land independently. I synthesize once they're back.

---

## Cowork's parallel work while research runs

Drafting the **architecture spec** in parallel with research:
- Module structure
- Plugin interfaces for level_source / arrival / confirmation / stop / target
- Strategy registry pattern
- Per-strategy state management
- Configuration model
- Daily report extensions for per-strategy attribution

When research lands, I update the architecture with research-informed specifics. Manny reviews. Then CC builds.

---

## The next directive will be a unified design doc

When research is in and architecture is drafted, the output is one comprehensive design doc covering:

1. **The principle** (already locked: healthy fluctuation framework)
2. **Universe definition** (from universe selection research)
3. **Strategy portfolio** (4-6 strategies from candidate strategies research)
4. **Per-strategy spec** (rigorous definitions of level_source, arrival, confirmation, stop, target)
5. **Architecture** (plugin pattern, registry, state, config)
6. **Backtest plan** (from backtest infrastructure research)
7. **Validation criteria** (when is a strategy "ready" for paper, when ready for real money)
8. **Build plan** (parallel workstreams CC can spawn)
9. **Timeline** (paper validation through July, real-money decision early August)

Manny reviews and iterates. Then build directive. Then CC builds with multiple parallel agents.

---

## What's NOT changing

- **6/15 squeeze-only real-money:** stands
- **WB retirement:** stands (the new framework is successor, not extension)
- **Monday production checklist:** unchanged, CC works it in parallel with planning
- **L2 build plan:** continues, Phase 7 stays parked but informs strategy candidates
- **All Saturday ships** (FCHL, force-exit, dead-tape, L2 async): stand

---

## Tone — for me, not for you

I've been falling into "this will take weeks" framing repeatedly tonight. Each time, the right correction was "CC works fast, focus on planning." That's a recurring bias I need to track. **Going forward, every directive must distinguish between planning time (real) and build time (compressed by CC's capabilities).** I'll stop attaching wall-clock estimates to build phases unless they have external blockers (market data subscription approvals, weekend market closures, etc.).

The framework build, once specified, is days of CC work, not weeks. The bottleneck is making sure the spec is right.

---

## Reports owed

| When | Report | Owner |
|---|---|---|
| Research completion (parallel) | 5 research reports | Cowork |
| Post-research synthesis | Unified architecture + strategy portfolio + build plan doc | Cowork |
| Awaiting Manny review | Design doc walkthrough | Manny |
| Post-Manny approval | Build directive | Cowork |
| Build start | Parallel workstreams CC spawns | CC |
| Monday EOD (separate workstream) | Daily production breakdown | CC |
| Friday 5/22 (separate workstream) | 5-day squeeze evaluation | CC |

The framework planning and the squeeze production validation run in parallel through next week.

---

## What I want from Manny while research runs

If you have specific examples of "healthy fluctuation" charts you can point to — symbols + dates + timestamps — they'd help calibrate the framework's level/confirmation criteria. We have your audit data already, but if you remember specific *winners from your manual paper trading* (not the bot's WB trades) that exemplify what you mean by healthy fluctuation, those become validation cases.

Not blocking, just helpful. I'll proceed with synthesis from research + existing data if you don't have specific examples to flag.

---

## Files referenced

- `DIRECTIVE_2026-05-17_HEALTHY_FLUCTUATION_FRAMEWORK.md` (the principle named)
- `DIRECTIVE_2026-05-17_BOT_VS_HUMAN_REFRAME.md` (the WB retirement)
- `cowork_reports/2026-05-17_loser_forensic_synthesis.md` (the data driving the reframe)
- `trading_notes_volume_profile_strategy.md` (the video extraction)
- `archive/scripts/l2_*.py` (L2 infrastructure now central to confirmation)
- `squeeze_detector_v2.py` (existing working level-reaction instance)
- `wave_breakout_detector.py` (retiring)
- 5 research reports incoming
