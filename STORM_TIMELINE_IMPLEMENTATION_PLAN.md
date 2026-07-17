# Curated Storm Timeline Implementation Plan

This document keeps the storm-to-outage feature aligned with the agreed scope:
extend the existing website, use one scientific generator, begin with one
curated HRRR-era storm, and defer arbitrary dates and Monte Carlo simulation.

## Phase 1 — Prepare one storm timeline — complete

- Tropical Storm Isaias is the only curated timeline.
- The window contains 24 hourly frames from 2020-08-04 06:00 UTC through
  2020-08-05 05:00 UTC.
- Every frame contains HRRR surface gusts, aligned one-hour precipitation, and
  six-hour antecedent precipitation on the existing 41×65 Connecticut grid.
- `data/connecticut_storm_timelines.js` is the shared weather source that the
  outage model and map visualization will both consume.
- The existing representative-hour file remains available until the later
  model and UI migration is verified.
- Automated checks cover timestamps, dimensions, finite values, rainfall
  accumulation, and movement of the damaging wind footprint.

## Phase 2 — Generate outages over time — complete

- The existing JavaScript model and Worker consume the curated hourly frames;
  no second generator was added.
- Customer exposure is calculated once. Wind, six-hour antecedent rain,
  network exposure, and Gaussian-smoothed impact are calculated for each hour.
- Segment risk is accumulated across the storm, then each unique sampled
  segment receives an occurrence time from its own hourly risk distribution.
- The seeded Isaias run produces exactly 2,000 unique locations × 50 customers,
  with `occurredAt`, `stormFrameIndex`, and local hourly weather diagnostics.
- Worker output includes 24 transferable Wind, Rain, Severity, Raw Impact, and
  Smoothed Impact frames for the existing map to animate in Phase 3.

## Phase 3 — Animate the existing map — complete

- The generated-scenario card now contains compact Play/Pause and hourly
  timeline controls; no new page or permanent sidebar section was added.
- Wind, one-hour rain, six-hour rain, weather severity, raw impact, and
  Gaussian-smoothed impact are rendered from the Worker's model-used arrays.
- Fixed storm-wide color scales keep frames comparable and low values are
  transparent, avoiding the former gray-rectangle appearance.
- Outage markers appear at `occurredAt` and remain visible as playback moves.
- The existing right-side checkboxes remain the master controls for outage,
  weather/impact, grid, substation, and review layers.
- The curated Isaias animation was verified in the actual local website,
  including autoplay, restart, scrubbing, surface selection, and layer hiding.

## Phase 4 — Restoration handoff and verification — complete

- The Plan restoration action stops playback, moves the map to the final storm
  frame, and passes the complete accumulated 2,000-location set through the
  existing restoration adapter and scheduler. The slider never changes that
  input.
- The website states the modeling boundary explicitly: the restoration clock
  begins after the curated storm passage. Concurrent damage and repair remain
  deferred.
- A visible contract summary verifies 100,000 initial customers, 100,000
  restored customers, and zero remaining customers after scheduling.
- With the same seed, network, and 2,000-location contract, the hourly Isaias
  model shares 1,613 selected segments (80.65%) with the old representative-
  hour model. The timeline centroid shifts about 0.12° east and 0.06° north,
  and adds occurrence times spanning 17:00–00:00 UTC. This confirms that the
  time series preserves broad storm signal while changing placement rather
  than merely decorating the old result.
- The browser no longer loads `connecticut_storm_wind.js`. That snapshot cache
  and generator API remain only for offline regression comparison and older
  research scripts; they are not a second professor-facing website pathway.
- Automated and in-browser workflow checks cover final-frame handoff, exact
  customer accounting, the zero endpoint, and the restoration curve.

## Explicitly deferred

- Arbitrary dates or live browser HRRR downloads
- Monte Carlo outage generation
- Pre-2014 storms and ERA5
- Claims of predictive accuracy before validation against observed outages
- Concurrent storm damage and restoration
