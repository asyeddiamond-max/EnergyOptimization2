# Design decisions: outage-location model (Alex Luo) vs the calibrated pipeline

Context: `feature/outage-location-simulator` (Alex Luo) replaced the original
placement + parts of the scheduler with a cleaner, tested, Worker-based model.
This document records, for each contested design point, which approach we keep
and **why, measured against the end goal of a publishable result** (crew /
restoration-time validation for Connecticut against public data).

Guiding principle for a paper: **a choice is "better" if it is validated against
independent real data, or if it is necessary to represent a real phenomenon.**
Cleaner code does not win a modeling argument; reproducing EAGLE-I does.

---

## 1. Large-storm outage stranding  →  FIXED (not a mine-vs-Alex choice)

Alex's refactor used the approximate `nnGridFindVisible` (100-ring cap) for
N>5000. On a storm's long tail the nearest discovered-undone outage can sit
beyond the cap, so it returned -1 and the run threw "lost track" (190-902
outages on the 5 biggest storms). Fixed by falling back to the exhaustive
`linearFindVisible` when `anyDiscoveredUndone()` proves work exists. Calibration
went 12/17 -> **17/17**. Alex's bug, now fixed; keep the fix.

## 2. Per-outage customers: flat 50 (Alex) vs geography-driven (original)  →  KEEP ORIGINAL for the paper

- **Alex:** every outage represents exactly 50 customers; total = 50 x nOutages.
  Enforced in the model, the adapter contract, and a test.
- **Original:** each outage inherits `popServed` from its feeder's population /
  segment count, so urban outages weigh more than rural ones. Emergent.

**Measured:** the original's totals land within ~2-4% of EAGLE-I peaks (Dec 2023
84,608 vs 86,770; Isaias 607,933 vs 632,632). Alex's flat 50 overshoots every
calibrated storm by ~65-68% (Dec 2023 -> 142,500) and cannot reproduce a real
peak by construction.

**Decision: prefer the original geography-driven counts, but this is NOT a
publishing blocker.** Two reasons it does not block the paper: (a) the paper's
customer PEAKS come from EAGLE-I directly (they are measured, not model-
predicted), and (b) the restoration-TIME calibration depends on outage count +
crews, not per-outage customers. Flat-50 only bites if the model is used to
PREDICT a customer peak (it overshoots 65-68%) or through customer-weighted
dispatch (a second-order effect on timing). So this is an interactive-display /
model-fidelity improvement, not a gate. A reviewer would still reject "our model
predicts the peak" with a flat constant, so if we ever make that claim, fix this
first.

*Not yet implemented in Alex's model* because it is a genuine modeling change:
the exposure surface exists (`relativeCustomerExposure`), but mapping it to an
absolute per-outage customer count needs a calibration constant and a contract +
test change. Best done deliberately, ideally with Alex. Until then the
calibration/paper path uses the original counts; Alex's model stays the
interactive front-end with its flat-50 clearly labeled.

## 3. Convective wind & the 35 mph threshold: July 2026 = zero outages  →  KEEP NCEI point reports (original)

This is the same decision as #4, surfacing as a symptom. At the default 35 mph
threshold Alex's model produces **zero** outages for July 2026, because its only
wind input is the HRRR grid, whose max IN-STATE gust for that storm is 27.6 mph
(the 40.4 peak is offshore). The real event had ~80 mph gusts.

The fix is NOT to lower the threshold — that would make every minor storm
explode. The fix is that HRRR's 3 km grid **systematically under-resolves
convective/tornadic wind**, so those events need point observations, not the
smoothed grid (see #4). This is a genuine, citable finding, not a bug.

## 4. NCEI storm reports: dropped (Alex) vs kept (original)  →  KEEP (original)

- **Alex:** removed `realReportWindMph` + `CONNECTICUT_STORM_EVENTS`; placement
  is HRRR-grid-only.
- **Original:** real NCEI point reports override the gridded wind where a
  tornado/severe cell is recorded.

**Measured:** for the May 2018 tornado outbreak, HRRR's gridded wind tops out at
~21 mph statewide while NCEI reports for the same event record 40-100 mph. A
gridded-only model structurally cannot represent CT's most damaging storm type
(tornado / severe convective). The tornado storms (May 2018, Aug 2020, Sep 2019)
and the flagship July 2026 all depend on this.

**Decision: keep the NCEI point-report overlay.** Re-integrating it into Alex's
model is a real effort (a point-severity overlay on top of the gridded surface),
so it is scoped, not yet done. This is arguably the single most publishable
finding here: *public gridded weather is insufficient for convective outage
modeling; point reports are required.*

## 5. Placement model overall: Alex's weather x exposure x Gaussian vs original wind-field + NCEI  →  KEEP BOTH; original is canonical for the paper

Neither is strictly better:

- **Alex's** is better engineered (dependency-free, Worker-isolated, versioned
  protocol, 39 tests, diagnostic surfaces) and more principled for BROAD storms
  (customer exposure x thresholded wind x rain, boundary-aware smoothing).
- **Original's** is validated end-to-end (17/17 restoration-time calibration,
  EAGLE-I peak match 2-4%) and handles convective/tornado events via NCEI.

**Decision:** Alex's model is the **interactive / visualization** engine; the
**original placement is canonical for the calibration and the paper**, because
that is the pipeline validated against EAGLE-I. A paper cites the validated
pipeline and can describe Alex's model as an alternative explored. If we want
Alex's model to become canonical, it must first (a) adopt geography-driven
customers (#2) and (b) re-integrate point reports (#3/#4), then WIN a head-to-head
bake-off on the 17-storm EAGLE-I calibration. The harness to run that bake-off
now works.

---

## What is done vs. pending

| # | decision | status |
|---|---|---|
| 1 | stranding fix | DONE (17/17) |
| 2 | geography-driven customers | decided (original); paper uses it, Alex-model change pending |
| 3 | July 2026 threshold | decided (it's the #4 finding, not a threshold tweak) |
| 4 | keep NCEI point reports | decided (keep); re-integration into Alex's model pending |
| 5 | canonical placement | decided (original canonical for paper; Alex's for interactive) |

Infrastructure adopted from Alex unconditionally (strictly better): the JS test
suite, the Web Worker pattern, and the versioned protocol.
