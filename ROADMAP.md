# Roadmap — Advisor Feedback Incorporation Plan

This document captures the advisor feedback on the Hartford County simulation
and turns it into an actionable, prioritized plan. It is the planning companion
to the development journal (`JOURNAL.html`) and research context
(`Hartford_Grid_Research_Context.docx`).

**Status as of this writing:** The Realism Fix Phases 1–3 are done
(hierarchical restoration, tiered priority, weather window). Phase 4
(switching/back-feed) is deferred. The advisor feedback below reshapes the
priority order going forward — several feedback items are higher-value than
Phase 4 and should come first.

---

## 1 · The feedback, organized by theme

Every point from the advisor feedback, grouped. Items marked ✅ are already
partially covered by what's built; ⏳ are new.

### Theme A — The restoration curve (orientation & emphasis)
- ⏳ **Flip the curve:** show *customers WITHOUT power* going from HIGH → ZERO
  over time, not customers-restored going up. "Turn your graph upside down."
  This is the standard utility restoration curve ("the second half of the curve").
- ⏳ **Time-series emphasis:** the curve is the core output metric; everything
  should produce / compare against it.
- ✅ We already compute a customers-restored-over-time curve; this is a
  re-orientation + relabel, not new computation.

### Theme B — Crew model: temporal & behavioral
- ⏳ **Crews vary over time (ramp):** crew count is a time series, not a fixed
  number. See the ~10-year-old David Wanik paper that models crews-over-time
  for Connecticut.
- ⏳ **Work rates:** ~2 outages per crew per day as a standard rate.
- ⏳ **Bulk crews at STATE level, back-calculated to county:** the DW paper
  knows statewide crew counts and infers county-level presence. "Know where
  outages are and assume where the crew is."
- ⏳ **Out-of-town crews are slower:** mutual-aid crews don't know the area,
  have limited communication, get lost. (We have mutual-aid *waves* ✅ but not
  the *slower-because-unfamiliar* factor ⏳.)
- ⏳ **Triple-time pay / big-storm drag:** behavioral/social-science factor —
  big storms can drag out because of pay incentives and fatigue.
- ✅ **Waiting for tree crews / cops to clear roads:** partially covered by
  crew specialization (line vs tree) + road multiplier; could be deepened.
- ⏳ **Crew "stickiness" (the key dispatch critique):** *"If a crew is in New
  Haven, they wouldn't drive to stores. If they start on a substation or
  circuit, they stay on it until it's done."* Real crews work an assigned
  area/circuit to completion — they don't bounce to the global nearest outage.
  Our greedy currently bounces. **This is the single most important realism
  correction the advisor raised.**

### Theme C — Real data (replace synthetic where possible)
- ⏳ **Real substations as point data (ISO New England):** don't simulate
  substation placement — use the real ISO-NE substation dataset, keep the real
  substation names. Build synthetic powerlines *from* the real substations.
- ⏳ **Real crew counts / daily recounts for CT:** from the DW paper,
  newspapers (Hartford Courant, etc.), and the Journal of Homeland Security.
  "Put data in the paper since stuff disappears."
- ⏳ **Eversource outage map:** real outage data source.
- ⏳ **Wind & temperature data (Colab notebooks provided):** drive storm
  generation from real weather rather than uniform-random outage placement.
  - Wind data Colab: (link provided by advisor — to be saved)
  - Temperature data Colab: (link provided by advisor — to be saved)
- ✅ **Calibration framework already built** (`/api/calibrate`) — ready to
  receive this real data.

### Theme D — Storytelling, visualization & comparison
- ⏳ **Depict real big hurricanes / biggest storms** (Sandy, Isaias, 2024
  events) and visualize what those outages looked like.
- ⏳ **Compare states and compare counties;** compare state *preparedness* in
  response to hurricanes.
- ⏳ **Map storms** (storm track overlays).
- ⏳ **CT-specific vegetation/farmland factor:** Connecticut (and NY, MA) have
  very large trees + farmland; tree-grid interaction is a unique, dominant
  outage driver vs. e.g. Florida. "See how trees falling down can impact
  outages."
- ⏳ **"Tell a story with data":** what crews did vs. what they could have done;
  the 2024 USA restoration story; crew-preparedness narratives from newspaper
  crews-per-day data.

### Theme E — Academic framing & math
- ✅ **David Wanik papers** — already cited in the research context doc.
- ⏳ **Journal of Homeland Security** — add as a venue/source.
- ✅ **"Knows the term for greedy"** — the advisor recognizes our heuristic is a
  greedy scheduler; this should be formalized in the math write-up.
- ⏳ **Math formalization** — "week after next we talk more about the math."
  Formalize the greedy, the restoration curve, and the crew time-series model.

---

## 2 · Prioritized implementation plan

Ordered by leverage (realism/value ÷ effort), with dependencies noted.

### Track 1 — Quick wins (frontend, low effort, high value)
1. **Flip the restoration curve** to customers-without-power, HIGH → ZERO.
   Explicitly requested, trivial (re-orient the existing curve). *Do first.*
2. **Curve polish:** label axes clearly (customers out vs hours/days), make it
   the headline output, support overlaying multiple runs for comparison.

### Track 2 — Crew stickiness (the #1 realism correction)
3. **Circuit/area assignment:** a crew assigned to a substation or circuit
   stays on it until done, instead of greedily bouncing to the global nearest
   outage. Likely implemented as: partition outages by substation/feeder,
   assign crews to partitions, each crew works its partition to completion.
   This directly addresses the advisor's main critique and pairs naturally
   with the deferred Phase 4 (switching). Medium effort.

### Track 3 — Temporal crew model (the DW-paper core)
4. **Time-varying crew availability:** replace the fixed crew slider with a
   crew *time series* — crews ramp up over days (generalizing the current
   mutual-aid waves). Parameterized so it can be fit to the DW-paper curves.
5. **Work-rate parameter** (~2 outages/crew/day) as an explicit, calibratable
   input.
6. **Out-of-town crew slowdown:** a per-crew familiarity factor that slows
   mutual-aid crews (longer travel/assessment).
7. **Big-storm drag** (triple-time/fatigue behavioral factor) as an optional
   modifier.

### Track 4 — Real data integration (needs data acquisition)
8. **Real substations (ISO New England):** swap synthetic k-means substations
   for the real ISO-NE substation point dataset with real names; generate
   synthetic feeders/laterals from those real anchor points. *Bounded data task.*
9. **Weather-driven storms:** use the advisor's wind/temperature Colab data to
   place outages by real storm exposure instead of uniform-random.
10. **Calibrate against real crew/outage counts** (DW paper, Eversource map,
    newspaper crews-per-day) using the existing `/api/calibrate` framework.

### Track 5 — Storytelling & comparison (the research narrative)
11. **Real-hurricane scenarios:** canned Sandy / Isaias / 2024 storms as
    pre-computed scenarios (extends the existing scenario library).
12. **Storm-track map overlays.**
13. **Multi-county / multi-state comparison view;** preparedness comparison.
14. **CT vegetation/farmland factor:** a tree-density-driven outage modifier
    capturing the unique CT/NY/MA tree-grid interaction.

### Track 6 — Math formalization (per "week after next we talk math")
15. Formal write-up of the greedy heuristic, the restoration-curve metric, and
    the crew time-series model; connect to the DW-paper methodology and the
    Journal of Homeland Security framing.

### Deferred from the prior roadmap
- **Phase 4 — Switching / back-feed:** still valuable, but now lower priority
  than crew stickiness (Track 2) and the temporal crew model (Track 3), which
  the advisor emphasized. Crew stickiness should be built first; switching can
  layer on after.

---

## 3 · Recommended next session order

1. **Track 1.1 — flip the curve** (small, explicitly requested).
2. **Track 2.3 — crew stickiness** (the advisor's headline critique).
3. **Track 3.4–3.5 — temporal crew ramp + work rate** (DW-paper core).
4. **Track 4.8 — real ISO-NE substations** (once the dataset is in hand).

Items in Tracks 4–5 are partly gated on data the advisor is providing (ISO-NE
substations, wind/temp Colabs, crew counts). Tracks 1–3 can proceed immediately
with no external data.

---

## 4 · Data & links to collect (action items, mostly on the advisor side)

- [ ] ISO New England substation point dataset (with names)
- [ ] David Wanik ~10-year-old crews-over-time CT paper (PDF + the crew curves)
- [ ] Wind-data Colab notebook (link from advisor)
- [ ] Temperature-data Colab notebook (link from advisor)
- [ ] Eversource outage-map data export
- [ ] Newspaper crews-per-day figures (Hartford Courant, etc.) for big storms
- [ ] Journal of Homeland Security relevant articles

---

*The five realism toggles already shipped (customer-impact weighting, crew
specialization, hierarchical restoration, tiered priority, weather window)
remain in place and are compatible with everything proposed here.*
