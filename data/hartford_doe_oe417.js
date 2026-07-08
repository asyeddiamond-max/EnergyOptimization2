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
    // Sourced from live news coverage only (NBC CT, WFSB incl. its I-Team
    // preparedness investigation, WTNH, CT Mirror) -- there is no PURA
    // docket or after-action report yet, since this event is only days old
    // as of this writing. Treat this entry as lower-confidence than the
    // others above until an official filing supersedes it.
    date: "2026-07-04",
    event: "July 2026 Severe Thunderstorm Complex",
    type: "Severe Weather — Thunderstorms/Wind (non-tropical, no HURDAT2 track)",
    utility: "Eversource Energy",
    state: "CT",
    customers_affected: 103500,
    demand_loss_mw: null,
    duration_h: 72,
    restoration_complete: "2026-07-07",
    notes: "Peak ~94,000 (Eversource) + ~8,500 (UI). Hardest-hit towns per news " +
      "reports: Harwinton, Montville, New Britain, New Fairfield, Winchester. " +
      "CREW COUNT NOT DISCLOSED -- WFSB's I-Team asked Eversource directly how " +
      "many crews were pre-positioned and got no response; daily_crews is left " +
      "null rather than guessed. For scale context, use the comparably-sized " +
      "real events above instead: May 2018 (125,000 cust, peaked at 1,000 " +
      "crews) and Dec 2023 (89,000 cust, peaked at 700 crews) both suggest " +
      "peak crews in the 700-1,000 range is the realistic ballpark for an " +
      "event this size, not 200.",
    // Approximate -- pieced together from several point-in-time news snapshots
    // (WFSB "~40,000 without power" and "50,000+ remain" both dated July 5;
    // "98% restored" dated Monday July 6; "nearly all by Tuesday night" July 7),
    // not a single authoritative hourly outage feed.
    daily_pct_out: [1.0, 0.45, 0.02, 0.0],
    daily_crews: null,
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
];
