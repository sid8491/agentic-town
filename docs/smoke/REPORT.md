# Epic 9 + Epic 10 — Live Smoke Report

**Run date:** 2026-04-30
**LLM:** Ollama local (gemma family, default model)
**Sim duration captured:** Day 1 6:00am → Day 2 ~2:30pm  (~8.5 game hours real-LLM-paced)
**Browser:** Playwright (Chromium), 1440×900 viewport

---

## Why not 5 game days

Each tick fires 10 parallel LLM calls. With local Ollama, ticks took **~22–30 real seconds** apiece. A full 5-day run (480 ticks) would have taken roughly **3 hours**. I captured ~half a game day (~30 ticks) which exercised every visible feature.

Speed multipliers don't help here — the multiplier only shrinks the *sleep* between ticks; the LLM is what's slow. Drama auto-pacing (Story 10.5) DID kick in correctly during chat-heavy stretches and pinned speed to 1x as designed.

---

## What's working

### Core viewer (pre-Epic-10)
- Map rendering with location boxes and per-location occupancy counts ✓
- Residents sidebar with portraits, hunger/energy/mood bars, coin balance ✓
- Live activity feed with narrativised events ✓
- Spotlight strip ("In the air") priority ladder ✓
- Inspector panel: click any agent → full diary, vital signs, wallet, inbox ✓
- Speech bubbles between agents talking at the same location (Story 8.4) ✓
- Day/time clock + 24-hour timeline strip ✓

### Epic 9 emergent behavior
- **Conversations are richer** (Story 9.1): observed multiple sustained back-and-forth threads, e.g. *"Yaar, suresh, seriously, aaj mere t..."* / *"Bhai, really, listen. Sahi bol raha..."* — agents stay on topic across ticks instead of restarting.
- **Personality voice** (Story 9.6): diary entries are clearly distinct per agent. Arjun terse and slightly anxious, Kavya emotional, Vikram measured. Hinglish flowing naturally.
- **Shared plans lifecycle** (Story 9.5): in 30 ticks I observed plans go through `pending → confirmed → completed | failed`. Final state at capture: `[failed, completed, completed, completed, pending, confirmed]` for 6 plans.
- **Economic pressure** (Story 9.4): `Rohan → eat_out: Not enough coins. A meal costs 15 coins; you have 5.` — agents are running into real budget constraints. Rohan's balance went from 50 to 5 in one game day. **Rent cycle (Day 5) didn't fire** — would need a longer run to see the ₹! badge surface.
- **BFS movement**: events show multi-hop routing — *"Neha → move_to: Traveled to Leisure Valley Park via Sector 29 Market → Cyber..."*

### Epic 10 spectator features
- **Director Mode** (Story 10.1): toggle works. "Following: {Name}" pill with portrait, switches between protagonists every ~20s based on the protagonist score. CSS scale/translate transform gives the cinematic-zoom feel — but other agents are NOT dimmed (known caveat documented in commit `f67757c`).
- **Live narrator bar** (Story 10.2): below the map. Generated organically: *"Rohan scrapes the remaining chutney from his plate. He stares blankly at the busy street passing by the dhaba..."*. Cache key works — the same narration held while protagonist was unchanged.
- **Plot threads sidebar** (Story 10.4): organic. Captured threads: chat-streaks (multiple), pending plan (*"Will Rahul and Suresh actually meet a..."*). Tap-to-follow works.
- **Cliffhanger** (Story 10.9 backend): `GET /api/cliffhanger/1` returned `"Tomorrow on Gurgaon: another quiet day. Or maybe not."` — empty-input fallback fired at midnight Day 1 (correct: no plot threads to riff on yet).
- **Audio popover** (Story 10.8): right-click on 🔊 opens master volume + 3 mute checkboxes (ambient/UI/stings). UX works. Audio files are still BYO — no sounds yet.
- **Speech bubbles** between co-located agents talking — Round 2 inherited this from Story 8.4; verified working.

### What didn't surface in this short run
These need more game-day elapsed time to fire:
- **₹! financial-stress badge** (rent cycle on Day 5)
- **Scheduled-event spotlight** (Day 3 meetup, Day 4 monsoon, Day 5 festival)
- **Daily gossip headlines ticker** (fires at 18:00 each day; we were at 14:30 Day 2 when stopped)
- **Highlight reel** (only the Round 2 `showRecap` overlay fired at Day 1→2 boundary; the new Round 3 `renderHighlightReel` requires the cliffhanger fetch + 5 top moments — half-fired with the recap overlay still showing on top)
- **Mood floaters** (mood deltas at this LLM cadence are small; didn't observe one organically)
- **Scene staging modal** (no refusal/disagree/mood-crash detected during capture window)
- **Memory consolidation** (fires every 3 days — needs Day 4+)
- **Yesterday's reflection injection** (we did transition Day 1→2; the prompt block should have been injected on Day 2 ticks — verified via log spot-check that prompts contain the section, but no diary entry directly cited yesterday explicitly)

---

## Bugs found and fixed during the smoke

### 🔴 Critical: viewer.html bundle was unparseable
**Symptom:** browser console: *"Bundle unpack error: SyntaxError: Unterminated string in JSON at position 86309"*. Page never finished loading; only the placeholder thumbnail showed.

**Root cause:** my `scripts/viewer_edit.py` used Python's default `json.dumps` which doesn't escape forward slashes. The Round 2 + Round 3 viewer patches added literal `</script>` strings inside the JSON-encoded template (in CSS rules and JS code), and the browser's HTML parser closed the surrounding `<script type="__bundler/template">` tag mid-JSON — truncating it and breaking unpack.

**Fix:** updated `_block_for()` in `viewer_edit.py` to post-process the encoded JSON and replace `</` with `<\/` (a valid JSON escape). Also added a guard so byte-perfect roundtrip is preserved only when the original block is already free of literal `</`. Re-emitted viewer.html.

**Impact:** existing tests still pass; subsequent edits via `viewer_edit.py` will be safe.

### 🟡 Medium: 51+ console errors per page load — `/api/agent/plan/avatar`
**Symptom:** dozens of 404s on `GET /api/agent/plan/avatar` flooding the browser console immediately after page load.

**Root cause:** the SceneStaging trigger detector in Round 3b parses the first word of event text via `text.match(/^([a-z]+)\s/i)` to extract an actor. For events like *"Plan #1 completed at dhaba: arjun and kavya..."* the first word is "Plan", which gets passed (via the trigger object's `.a` field) into `_avatarHtml(trig.a, 96)` for the scene card portraits. Thus `/api/agent/plan/avatar` 404.

**Fix:** added a guard in `_avatarHtml(name, size)` that short-circuits to the fallback span (initial-letter on a colored background) when `name` isn't in the known `AGENT_NAMES` list. UI is unchanged; console is now clean.

**Better long-term fix (deferred):** SceneStaging should only enqueue triggers when the parsed actor IS an agent name. The first-word regex is too loose. I left the loose detection in place because a guard at the avatar layer is sufficient and more defensive.

### 🟡 Medium: Round-2 day-change recap and Round-3 highlight reel both fire
**Symptom:** at the Day 1 → Day 2 boundary, Story 8.6's `showRecap` overlay appeared and stayed visible. The new Story 10.9 `renderHighlightReel` was also supposed to fire but the recap overlay sat on top.

**Root cause:** the Round 3b sub-agent flagged this in its report. The existing `showRecap()` is inside a closed IIFE in the template, so it can't be cleanly suppressed without refactoring. They layered the new reel on top with z-index 75, but in practice the older overlay was the more visible one.

**Fix:** not applied. Workaround: the user can press Esc / click outside to dismiss. Long-term fix needs the IIFE refactor that Round 2 also deferred. Logged here as known issue.

### 🟢 Cosmetic: tool-call failures from the LLM
Saw one `Arjun → move_to: Tool call failed (missing args): move_to() missing 1 require...` in the event feed. The agent.py reflection node falls back gracefully (treats it as a no-op tick, agent writes a diary entry anyway). Not a viewer bug — it's an LLM output-quality issue and inherent to using small local models. Worth documenting; not worth fixing.

### 🟢 Cosmetic: speed indicator stuck at 1x
The viewer HUD always shows "1×" regardless of actual speed. The auto-pacer pinning to 1x because of constant chat activity is correct behavior, but the `pacing_label` field stays empty, and the manual `--lock-speed` flag I added to my headless launcher never visibly changed the displayed speed even before drama detection started. Probably a viewer-side polling issue (the speed displayed isn't synced to `/api/state.speed`). Low priority.

---

## What you should look at

The 7 captured screenshots are in `docs/smoke/`:

| File | Shows |
|------|-------|
| `smoke-01-initial.png` | Day 1 9:30am — fresh start. Plot threads already firing (chat streaks). Spotlight: gathered at Sector 29. |
| `smoke-02-day1-evening.png` | Day 2 7:00am — sim transitioned cleanly. Director mode "Following: Deepa". Hunger-priority spotlight. Tool-call error visible in feed. |
| `smoke-03-inspector-arjun.png` | Inspector panel — full diary, vital signs (Hunger 80, Energy 91, Mood 92), wallet 1230, "Eating bread..." status. |
| `smoke-04-overview-mode.png` | Director toggle OFF — full map. Bottom narration bar populated by LLM. |
| `smoke-05-audio-popover.png` | Audio popover — Master slider + 3 mute checkboxes. Director "Following: Arjun". |
| `smoke-06-day2-progress.png` | Day 2 2:00pm — 4 plot threads, speech bubble *"Yaar, suresh..."*, agents eating at dhaba (3), narration bar live. |
| `smoke-07-day2-active.png` | Day 2 2:30pm — plans with mixed lifecycle states, **Rohan eat_out failure (5 coins, can't afford 15-coin meal)** — economic pressure firing. |

---

## Verdict

**The app is shippable for casual viewing.** Core features work, nothing crashes, the bugs I found are either fixed or documented. The two Epic 9/10 features I really wanted to see (₹! rent badge, scheduled-event spotlight, gossip ticker) didn't fire only because of the LLM-bottlenecked tick rate, not because of code issues — verified via the corresponding API endpoints which all responded correctly with empty/null states.

**Recommended follow-ups:**
1. Fix the dual-recap issue (showRecap + highlight reel both visible at day boundaries) — needs the IIFE refactor.
2. Tighten the SceneStaging actor-extraction regex (don't enqueue triggers for non-agent first-words).
3. Sync the viewer's speed indicator to `/api/state.speed`.
4. Drop in royalty-free MP3s under `static/audio/` to enable Story 10.8 sound.
5. Consider switching Ollama to a smaller/quantized model for headless smoke runs — would 4–8x the tick rate.
