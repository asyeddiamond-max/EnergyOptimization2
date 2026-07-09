// DOE OE-417 Electric Disturbance Events affecting Connecticut.
// Source: U.S. Department of Energy, Office of Electricity
// https://www.oe.netl.doe.gov/OE417_annual_summary.aspx
// Filtered to events affecting Eversource CT / Hartford County.
// Used for calibration: comparing simulated restoration curves against
// real reported outage durations and customer counts.
//
// daily_pct_out: fraction of customers still without power at end of each day
//   Sources: PURA Docket 20-08-03, Eversource after-action reports,
//   CT DEEP storm reports, news coverage (CT Mirror, Hartford Courant).
//
// daily_crews: total crews deployed each day (line + tree + support).
//   Sources: Eversource press releases, PURA filings, CT Mirror reporting.

window.HARTFORD_DOE_OE417 = [
  {
    date: "2020-08-04",
    event: "Tropical Storm Isaias",
    type: "Severe Weather — Thunderstorms/Wind",
    utility: "Eversource Energy",
    state: "CT",
    customers_affected: 632632,
    demand_loss_mw: null,
    duration_h: 264,
    restoration_complete: "2020-08-14",
    notes: "11-day restoration; 504 line crews + 235 tree crews day 1, peaked at 4500+",
    daily_pct_out: [1.0, 0.92, 0.78, 0.60, 0.42, 0.28, 0.16, 0.08, 0.03, 0.01, 0.0],
    daily_crews: [739, 1200, 2100, 3280, 3800, 4500, 4200, 3500, 2000, 800, 200],
  },
  {
    date: "2012-10-29",
    event: "Hurricane Sandy",
    type: "Severe Weather — Hurricane",
    utility: "Connecticut Light & Power (now Eversource)",
    state: "CT",
    customers_affected: 625000,
    demand_loss_mw: null,
    duration_h: 264,
    restoration_complete: "2012-11-09",
    notes: "11-day restoration across CT; some areas 14+ days",
    daily_pct_out: [1.0, 0.90, 0.75, 0.58, 0.40, 0.27, 0.15, 0.08, 0.04, 0.01, 0.0],
    daily_crews: [600, 1100, 2000, 3000, 3600, 4000, 3800, 3000, 1800, 600, 150],
  },
  {
    date: "2011-08-28",
    event: "Tropical Storm Irene",
    type: "Severe Weather — Hurricane/Tropical Storm",
    utility: "Connecticut Light & Power",
    state: "CT",
    customers_affected: 670000,
    demand_loss_mw: null,
    duration_h: 288,
    restoration_complete: "2011-09-09",
    notes: "12-day restoration; worst in CL&P history at the time",
    daily_pct_out: [1.0, 0.93, 0.82, 0.68, 0.52, 0.38, 0.25, 0.15, 0.08, 0.04, 0.01, 0.0],
    daily_crews: [500, 900, 1600, 2500, 3200, 3800, 3600, 3000, 2000, 1200, 500, 100],
  },
  {
    date: "2011-10-29",
    event: "October Nor'easter (Snowtober)",
    type: "Severe Weather — Winter Storm",
    utility: "Connecticut Light & Power",
    state: "CT",
    customers_affected: 830000,
    demand_loss_mw: null,
    duration_h: 264,
    restoration_complete: "2011-11-09",
    notes: "Unprecedented early snowstorm; trees still in leaf; worst CT outage event",
    daily_pct_out: [1.0, 0.94, 0.83, 0.70, 0.55, 0.38, 0.22, 0.12, 0.05, 0.02, 0.0],
    daily_crews: [400, 800, 1800, 3000, 4000, 4800, 4500, 3500, 2000, 800, 200],
  },
  {
    date: "2018-05-15",
    event: "May 2018 Tornadoes / Derecho",
    type: "Severe Weather — Thunderstorms/Tornado",
    utility: "Eversource Energy",
    state: "CT",
    customers_affected: 125000,
    demand_loss_mw: null,
    duration_h: 192,
    restoration_complete: "2018-05-23",
    notes: "Multiple tornadoes confirmed in CT; concentrated damage in Hartford County corridor",
    daily_pct_out: [1.0, 0.75, 0.50, 0.30, 0.15, 0.06, 0.02, 0.0],
    daily_crews: [300, 600, 900, 1000, 800, 500, 200, 50],
  },
  {
    date: "2021-08-22",
    event: "Tropical Storm Henri",
    type: "Severe Weather — Tropical Storm",
    utility: "Eversource Energy",
    state: "CT",
    customers_affected: 23000,
    demand_loss_mw: null,
    duration_h: 48,
    restoration_complete: "2021-08-24",
    notes: "Relatively minor for CT; most damage in coastal areas",
    daily_pct_out: [1.0, 0.30, 0.0],
    daily_crews: [200, 300, 100],
  },
  {
    date: "2024-01-10",
    event: "January 2024 Wind Storm",
    type: "Severe Weather — High Winds",
    utility: "Eversource Energy",
    state: "CT",
    customers_affected: 52000,
    demand_loss_mw: null,
    duration_h: 72,
    restoration_complete: "2024-01-13",
    notes: "60+ mph wind gusts; scattered damage across Hartford County",
    daily_pct_out: [1.0, 0.50, 0.10, 0.0],
    daily_crews: [250, 500, 400, 100],
  },
  {
    date: "2023-12-18",
    event: "December 2023 Nor'easter",
    type: "Severe Weather — Winter Storm",
    utility: "Eversource Energy",
    state: "CT",
    customers_affected: 89000,
    demand_loss_mw: null,
    duration_h: 96,
    restoration_complete: "2023-12-22",
    notes: "Heavy wet snow + wind; significant tree damage in rural Hartford County towns",
    daily_pct_out: [1.0, 0.60, 0.25, 0.08, 0.0],
    daily_crews: [300, 600, 700, 400, 100],
  },
  {
    // UPDATED 2026-07-08 from WFSB's follow-up accountability piece (governor +
    // gubernatorial candidates pushing Eversource for answers), which supersedes
    // this dataset's original day-of-storm estimate below. Still sourced from
    // news coverage only (no PURA docket/after-action report yet) -- treat as
    // lower-confidence than the pre-2026 events above until an official filing
    // lands, but higher-confidence than the original entry since it's a
    // deliberate post-storm accounting rather than live/evolving snapshots.
    date: "2026-07-04",
    event: "July 2026 Severe Thunderstorm Complex",
    type: "Severe Weather — Thunderstorms/Wind (non-tropical, no HURDAT2 track)",
    utility: "Eversource Energy",
    state: "CT",
    customers_affected: 180000,
    demand_loss_mw: null,
    duration_h: 96,
    restoration_complete: "2026-07-08",
    notes: "Peak >180,000 Eversource CT customers (WFSB 7/8 follow-up; " +
      "supersedes this entry's original ~94,000 estimate, which came from " +
      "day-of news snapshots that understated the true peak). Hardest-hit: " +
      "Torrington and Harwinton specifically named in the follow-up coverage " +
      "(Montville, New Britain, New Fairfield, Winchester were named in the " +
      "original day-of reports). CREW COUNT NOW DISCLOSED: 702 crews total " +
      "at peak, 230 (~33%) Eversource direct staff, remainder contractor/" +
      "mutual-aid -- in line with this dataset's May 2018 (1,000 crews) and " +
      "Dec 2023 (700 crews) as the realistic ballpark for an event this size. " +
      "Response was criticized as unusually slow to mobilize: Harwinton's " +
      "first selectman reported ~2 days with no Eversource crews visibly on " +
      "the ground, and the broader assessment was '36-48 hours before " +
      "substantial crews got on the ground' -- notably slower than this " +
      "dataset's other storms' initial ramp (most show meaningful crew " +
      "presence within 12-24h). Per the article, Eversource's pre-storm " +
      "forecast was 30 hours stale and focused on the wrong region (Southwest " +
      "CT) while missing the actual impact area (Torrington/Harwinton, NW " +
      "Litchfield County).",
    // Approximate -- pieced together from news snapshots plus the 7/8 "4 days
    // to restore" and "36-48h to substantial crews" framing, not a single
    // authoritative hourly outage feed. Shaped to reflect the documented slow
    // start (crews.day1 << crews.day2, unlike this dataset's faster-ramping
    // storms) rather than a smooth ramp.
    daily_pct_out: [1.0, 0.55, 0.15, 0.0],
    daily_crews: [80, 500, 702, 250],
  },
  {
    // NOTE: real sources conflict on the peak figure for this storm. Several
    // summaries say "more than 120,000 customers" lost power, but that
    // appears to be either a multi-state (CT+MA) figure or a pre-storm
    // worst-case projection ("several hundred thousand" was floated by
    // ctmirror.org before the storm hit) that didn't materialize for CT
    // specifically -- WFSB's hour-by-hour timeline article gives a much
    // smaller, specific peak: 13,665 Eversource CT customers at noon Monday
    // 2/23. Using that more granular, timestamped figure (plus UI's share,
    // for a combined ~15,000) rather than the vaguer "120,000+" claims.
    date: "2026-02-23",
    event: "Blizzard Calvin",
    type: "Severe Weather — Winter Storm (blizzard)",
    utility: "Eversource Energy",
    state: "CT",
    customers_affected: 15000,
    demand_loss_mw: null,
    duration_h: 40,
    restoration_complete: "2026-02-24",
    notes: "CT's first official blizzard in 8 years, but CT-specific impact " +
      "was much smaller than pre-storm projections -- Massachusetts took the " +
      "brunt (142,000 Eversource + 45,000 National Grid customers there). " +
      "700 crews pre-positioned in CT (from NH, MA, NY, NJ, PA, and Canada) " +
      "ahead of the storm per Eversource's own announcement. Eversource said " +
      "power would be fully restored by 11:45pm Tuesday 2/24 at the latest.",
    daily_pct_out: [1.0, 0.20, 0.0],
    daily_crews: [700, 700, 100],
  },
  {
    // LOWER CONFIDENCE than the other entries above. Real sources agree CT's
    // peak was "more than 120,000" Eversource customers (Wikipedia's March
    // 6-8, 2018 nor'easter summary, cross-checked against a separate news
    // search), but no source found gives a precise CT-specific restoration
    // completion date, and CT PURA Docket 25-12-13 (covering 43 storms from
    // 2018-2023 including this one) wasn't accessible in enough detail to
    // pull an exact figure. duration_h/daily_crews below are an ESTIMATE,
    // interpolated from comparably-scaled real wet-snow nor'easters already
    // in this file (Dec 2023: 89,000 cust / 96h / peak 700 crews; Snowtober
    // 2011: 830,000 cust / 264h / peak 4,800 crews) -- not sourced the way
    // the other entries are. Treat any simulator comparison against this
    // entry as a rougher sanity check, not a tight validation.
    date: "2018-03-07",
    event: "Winter Storm Quinn (nor'easter)",
    type: "Severe Weather — Winter Storm (heavy wet snow)",
    utility: "Eversource Energy",
    state: "CT",
    customers_affected: 140000,
    demand_loss_mw: null,
    duration_h: 120,
    restoration_complete: "2018-03-12",
    notes: "Part of a string of 4 nor'easters in 3 weeks (Riley, Quinn, Skylar, " +
      "Toby); Quinn specifically brought the heaviest, wettest snow of the " +
      "four to CT. Mutual aid crews came from MA, NH, and Canada. Included " +
      "in PURA's $933M storm-cost-recovery decision (Docket 25-12-13, " +
      "covering 43 storms 2018-2023) but a CT-specific restoration timeline " +
      "wasn't found independently -- duration_h and daily_crews here are " +
      "interpolated from comparable real events, not directly sourced.",
    daily_pct_out: [1.0, 0.55, 0.20, 0.05, 0.0],
    daily_crews: [500, 900, 1100, 700, 100],
  },
  {
    // Added as a real, well-documented THIRD spatially-concentrated/localized
    // storm (alongside May 2018 and July 2026 above), specifically to check
    // whether the model's workloadSlowdownMult miss on those two (opposite
    // directions -- May 2018 needs more slowdown, July 2026 needs less) is a
    // consistent pattern or was just 2 contradictory data points. Sourced
    // from live news only (NBC CT, WTNH, Fox61) -- no PURA docket dug up for
    // this specific event, though it likely appears in the same Docket
    // 25-12-13 storm-cost-recovery filing as Quinn above (43 storms,
    // 2018-2023 -- this one is just outside that window, in 2020).
    date: "2020-08-27",
    event: "Bethany-Hamden-North Haven Tornado + Severe T-storm",
    type: "Severe Weather — Thunderstorms/Tornado (non-tropical, no HURDAT2 track)",
    utility: "Eversource Energy",
    state: "CT",
    customers_affected: 54000,
    demand_loss_mw: null,
    duration_h: 96,
    restoration_complete: "2020-08-31",
    notes: "NWS confirmed an EF1 tornado (110 mph) touched down in Bethany " +
      "~3:55pm and tracked ~11 miles southeast through Hamden to North Haven " +
      "by 4:00pm. Branford was separately hit hardest by straight-line " +
      "severe-thunderstorm wind in the same system (99%+ of its Eversource " +
      "customers out), not the tornado path itself. Combined statewide peak: " +
      "~25,000 Eversource (11pm night-of) + ~29,000 United Illuminating. " +
      "Eversource crews: 380 total, 80 specifically assigned to Branford. " +
      "Response was notably FAST relative to July 2026 above -- Eversource " +
      "substantially complete for all towns except Branford by midnight " +
      "Friday (~32h after the storm), Branford by Saturday night (~56h); UI's " +
      "hardest system-rebuild areas cleared by Monday (~96h). daily_crews " +
      "shaped as a fast ramp (already near half of peak crews same-day) to " +
      "reflect this -- unlike July 2026's documented slow start, there's no " +
      "reporting here of a mobilization delay or public criticism of the " +
      "initial response.",
    daily_pct_out: [1.0, 0.15, 0.05, 0.02, 0.0],
    daily_crews: [200, 380, 150, 50, 10],
  },
  {
    // LOWER CONFIDENCE, similar caveat to Winter Storm Quinn above: sourced
    // from a real Eversource press release (confirmed real event -- CT
    // DEMHS partially activated its Emergency Operations Center the same
    // day, with NWS winter storm warnings specifically for Litchfield/
    // Tolland/Windham counties) and live news, but no precise peak crew
    // count or restoration-complete timestamp was found -- only "hundreds"
    // of crews plus named out-of-state mutual aid (IN, MO, OH, TN, TX, MA,
    // NH, Canada) and a same-day partial-restoration snapshot. duration_h
    // and daily_crews below are interpolated from Henri 2021 (closest real
    // neighbor by customer count: 23,000 cust / 48h / peak 300 crews) and
    // Jan 2024 (52,000 cust / 72h / peak 500 crews), not directly sourced.
    date: "2023-03-14",
    event: "March 2023 Nor'easter (elevation-dependent wet snow)",
    type: "Severe Weather — Winter Storm (heavy wet snow, elevation-dependent)",
    utility: "Eversource Energy",
    state: "CT",
    customers_affected: 26800,
    demand_loss_mw: null,
    duration_h: 72,
    restoration_complete: "2023-03-17",
    notes: "Rapidly-intensifying nor'easter, heaviest impact in higher-" +
      "elevation Litchfield County (consistent with 'heavy, wet snow' being " +
      "elevation-dependent per Eversource's own statement) -- a normal " +
      "within-storm geographic skew for a broad statewide system, not " +
      "spatially-confined the way the tornado/thunderstorm-complex entries " +
      "above are, so NOT flagged is_localized_reports. Peak ~26,800 " +
      "Eversource CT customers (12,800 restored + ~14,000 still out, both " +
      "as of 4pm on the storm day itself). Crews: 'hundreds' of Eversource " +
      "line/tree crews plus mutual aid from Indiana, Missouri, Ohio, " +
      "Tennessee, Texas, Massachusetts, New Hampshire, and Canada -- no " +
      "precise total given.",
    daily_pct_out: [1.0, 0.35, 0.08, 0.0],
    daily_crews: [250, 350, 200, 50],
  },
  {
    // Second real tornado/derecho-type event, added specifically to check
    // whether May 2018's gap (needs MORE workloadSlowdownMult than the
    // formula gives) is a real pattern for HRRR-grid-placed convective
    // severe weather, or was a one-off. NWS confirmed this as a genuine
    // "serial derecho" (Wikipedia's List of derecho events) on 2020-10-07,
    // a 320-mile-wide damage path across NY/MA/CT/RI. Real NCEI Storm
    // Events reports (15_fetch_storm_events.py, see
    // data/connecticut_storm_events.js key "2020-10-07") confirm 14
    // real CT thunderstorm-wind reports, 52-60kt, spanning Fairfield, New
    // Haven, Hartford, Tolland, and Windham counties -- a genuinely
    // statewide damage swath, unlike the Aug 2020 tornado's narrow single-
    // corner path, which is why this one is placed via the real HRRR grid
    // (12_fetch_hrrr_storm_wind.py, key "oct2020_derecho") like May 2018,
    // NOT synthetic town-centroid decay -- not flagged is_localized_reports.
    //
    // LOWER CONFIDENCE than most entries above: CT's peak (~90,000
    // Eversource customers) comes from a specific regional outage
    // comparison (NY ~230k, PA ~176k, ME ~117k, CT ~90k) cross-referencing
    // multiple news sources discussing the same NWS-confirmed event, but no
    // CT-specific crew count or restoration-complete date was found despite
    // extensive searching (this event got relatively little standalone CT
    // news coverage, possibly overshadowed by being just 2 months after
    // Isaias). duration_h (96) and crews (700) are interpolated from Dec
    // 2023 (89,000 cust -- nearly identical peak -- 96h, peak 700 crews),
    // the closest real neighbor by customer count, not directly sourced.
    date: "2020-10-07",
    event: "October 2020 Northeast Serial Derecho",
    type: "Severe Weather — Thunderstorms/Derecho",
    utility: "Eversource Energy",
    state: "CT",
    customers_affected: 90000,
    demand_loss_mw: null,
    duration_h: 96,
    restoration_complete: "2020-10-11",
    notes: "NWS-confirmed serial derecho, wind gusts 50-70mph, part of a " +
      "320-mile-wide damage path across NY, MA, CT, and RI (per Wikipedia's " +
      "List of derecho events). Regional peak outages: NY ~230,000, PA " +
      "~176,000, ME ~117,000, CT ~90,000. CT-specific crew count and " +
      "restoration-complete date not found independently -- duration_h and " +
      "daily_crews interpolated from Dec 2023 (near-identical customer " +
      "count). Treat the calibration ratio for this entry as informative " +
      "about wind-severity/repair-time modeling (which uses directly-" +
      "sourced real HRRR + NCEI wind data) more than about crew-ramp " +
      "timing (which is guessed).",
    daily_pct_out: [1.0, 0.55, 0.20, 0.05, 0.0],
    daily_crews: [400, 700, 500, 200, 50],
  },
];
