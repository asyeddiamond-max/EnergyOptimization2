"""
16_calibrate_against_real_storms.py -- headless validation harness.

Runs the REAL scheduler logic from 03_grid_simulation.html (extracted
verbatim, not reimplemented) inside an embedded V8 (py_mini_racer), once per
real historical storm in data/hartford_doe_oe417.js, and compares the
simulator's own restoration time against each storm's real documented
duration. This is the tool used to derive/tune deriveRampParams(),
discMaxTail, and workloadSlowdownMult in 03_grid_simulation.html -- rerun it
after touching any of those to confirm you haven't traded one storm's
accuracy for another's.

IMPORTANT: builds a completely FRESH V8 context per storm (reloading the
full script + all data each time). A shared-context version that just
mutated globals between iterations was tried first and gave inconsistent,
non-reproducible results for identical parameters -- some hidden module-
level state doesn't fully reset between calls. Don't "optimize" this back
to a shared context without re-verifying results stay stable.

Requires: pip install py_mini_racer

Usage:
    python 16_calibrate_against_real_storms.py
"""
from __future__ import annotations
import json
from pathlib import Path

from py_mini_racer import py_mini_racer

HERE = Path(__file__).parent
DATA = HERE / "data"


def _extract_script() -> str:
    html = (HERE / "03_grid_simulation.html").read_text(encoding="utf-8")
    start = html.index("<script>") + len("<script>")
    end = html.rindex("</script>")
    script = html[start:end]

    # Drop the real Leaflet map-init block (tiles, panes, legend) -- replaced
    # by a permissive Proxy stand-in below.
    i = script.index("// --- Map ---")
    j = script.index("legend.addTo(map);") + len("legend.addTo(map);")
    script = script[:i] + script[j:]

    # Drop PointCloudLayer/PolylineCloudLayer (real Leaflet canvas renderers,
    # meaningless headless) and stub both out instead.
    i = script.index("const PointCloudLayer = L.Layer.extend({")
    j = script.index("const outageLayer=L.layerGroup().addTo(map);")
    script = script[:i] + script[j:]
    script = (
        "class PointCloudLayer{constructor(){}addTo(){return this;}}\n"
        "class PolylineCloudLayer{constructor(){}setLines(){}addTo(){return this;}}\n"
        + script
    )

    # Drop the real boot IIFE (fetches boundary data over HTTP, irrelevant
    # here -- boundary/bitmap setup is done manually below instead).
    i = script.index("// --- Boot ---")
    return script[:i]


def _load_data_inject() -> str:
    def load(name):
        return json.loads((DATA / name).read_text(encoding="utf-8"))

    subs = load("connecticut_substations.json")
    crit = load("connecticut_critical_facilities.json")
    tracts = load("connecticut_census_tracts.json")
    towns_pop = load("connecticut_towns_population.json")
    canopy = load("connecticut_tree_canopy.json")
    towns_geo = json.loads((DATA / "connecticut_towns.geojson").read_text(encoding="utf-8"))
    flood_extra = load("connecticut_flood_corridors.json")
    doe_js = (DATA / "hartford_doe_oe417.js").read_text(encoding="utf-8")
    tracks_js = (DATA / "hartford_storm_tracks.js").read_text(encoding="utf-8")
    wind_js = (DATA / "connecticut_storm_wind.js").read_text(encoding="utf-8")
    events_js = (DATA / "connecticut_storm_events.js").read_text(encoding="utf-8")

    return f"""
window.CONNECTICUT_SUBSTATIONS = {json.dumps(subs)};
window.CONNECTICUT_CRITICAL_FACILITIES = {json.dumps(crit)};
window.CONNECTICUT_CENSUS_TRACTS = {json.dumps(tracts)};
window.CONNECTICUT_TOWNS_POPULATION = {json.dumps(towns_pop)};
window.CONNECTICUT_TREE_CANOPY = {json.dumps(canopy)};
window.CONNECTICUT_TOWNS_GEOJSON = {json.dumps(towns_geo)};
window.CONNECTICUT_FLOOD_CORRIDORS_EXTRA = {json.dumps(flood_extra)};
{doe_js}
{tracks_js}
{wind_js}
{events_js}
"""


_SHIM_TEMPLATE = r"""
var window = this;
window.addEventListener = function(){};
window._mask = null;
var __log = [];
console.log = function(...a){ __log.push(a.map(String).join(' ')); };
console.warn = console.log; console.error = console.log;

function setTimeout(fn, ms){ fn(); return 0; }
function setInterval(fn, ms){ return 0; }
function clearInterval(id){}
function clearTimeout(id){}

function _fakeElement(id){
  return {
    id, value: '', checked: false, textContent: '', innerHTML: '', className: '',
    style: {}, classList: { add(){}, remove(){}, contains(){return false;}, toggle(){} },
    addEventListener(){}, appendChild(){}, removeChild(){},
    getContext(){ return _fakeCtx(); },
    querySelectorAll(){ return []; }, querySelector(){ return _fakeElement('nested'); },
    closest(){ return _fakeElement('closest'); },
  };
}
function _fakeCtx(){
  return {
    clearRect(){}, fillRect(){}, beginPath(){}, arc(){}, fill(){}, stroke(){},
    moveTo(){}, lineTo(){}, closePath(){},
    createImageData(w,h){ return { data: new Uint8ClampedArray((w||1)*(h||1)*4), width:w, height:h }; },
    putImageData(){}, drawImage(){},
    set fillStyle(v){}, set strokeStyle(v){}, set lineWidth(v){}, set globalAlpha(v){},
    set lineJoin(v){}, set lineCap(v){},
  };
}

// All "advanced feature" checkboxes checked (matches the real page's
// defaults) so realistic-mode behavior matches what a user actually sees.
const _CHECKED_BY_DEFAULT = new Set([
  'realisticMode','customerPriority','crewSpecialization','hierarchicalMode','tieredPriority',
  'crewStickiness','stormDrag','soilSaturation','preStormStaging','weatherWindow',
  'crewTimeSeriesRamp','crewFatigueOT','floodZoneClosures','equipmentShortage',
  'customerCallbackLag','undergroundLines','switchingBackfeed','amiCoverage',
  'mutualAidTravel','roadClosure','windFieldWeighting','useServerToggle',
  'showCriticalFacilities','useCensusTracts',
]);
const _VALUE_DEFAULTS = {
  stormDurationH: '18', seedInput: '42',
  oSlider: '%(n_out)s', cSlider: '%(m_crew)s', stormTrackSelect: '%(track)s', fSlider: '5',
};

const document = {
  body: { dataset: {}, appendChild(){}, style:{} },
  getElementById(id){
    const el = _fakeElement(id);
    if (_CHECKED_BY_DEFAULT.has(id)) el.checked = true;
    if (_VALUE_DEFAULTS[id] !== undefined) el.value = _VALUE_DEFAULTS[id];
    return el;
  },
  createElement(tag){ return _fakeElement('created-'+tag); },
  querySelector(){ return _fakeElement('qs'); },
  addEventListener(){},
};

function _chainable(){ const o = {}; return new Proxy(o, { get(){ return (...a)=>_chainable(); } }); }
const L = new Proxy({
  // geoBounds() needs this to do real arithmetic, not just avoid throwing.
  latLngBounds(sw, ne){
    return {
      getSouth(){ return sw[0]; }, getWest(){ return sw[1]; },
      getNorth(){ return ne[0]; }, getEast(){ return ne[1]; },
    };
  },
}, { get(target, prop){ return prop in target ? target[prop] : (...a)=>_chainable(); } });
const map = _chainable();

function ImageData(data, w, h){ this.data = data; this.width = w; this.height = h; }
"""


def run_storm(script: str, data_inject: str, land_geo: dict,
              track: str, n_out: int, m_crew: int) -> tuple[float | None, float | None, str]:
    """Returns (simulated_total_time_h, simulated_total_customers, last-5-log-lines)."""
    shim = _SHIM_TEMPLATE % {"n_out": n_out, "m_crew": m_crew, "track": track}
    full = shim + "\n" + data_inject + "\n" + script

    ctx = py_mini_racer.MiniRacer()
    ctx.eval(full)
    ctx.eval(f"countyGeo = {json.dumps(land_geo)}; buildInsideBitmap(countyGeo);")
    ctx.eval(
        "var __gridDone=false; generateGrid().then(()=>{__gridDone=true;})"
        ".catch(e=>{__log.push('GRID ERROR: '+e);__gridDone=true;});",
        timeout=60_000,
    )
    ctx.eval(
        "var __stormDone=false; simulateStorm().then(()=>{__stormDone=true;})"
        ".catch(e=>{__log.push('STORM ERROR: '+e);__stormDone=true;});",
        timeout=30_000,
    )
    ctx.eval(
        "var __planDone=false; planRestoration().then(()=>{__planDone=true;})"
        ".catch(e=>{__log.push('PLAN ERROR: '+e);__planDone=true;});",
        timeout=45_000,
    )
    sim_h = ctx.eval("plan ? plan.totalTime : null")
    total_cust = ctx.eval("storm ? storm.totalCust : null")
    log_tail = ctx.eval("__log.slice(-5).join('\\n')")
    return sim_h, total_cust, log_tail


# (track_key, calibrated outage count, real peak crew count, real duration_h, label)
# Outage counts are pre-calibrated so each storm's simulated customer count
# lands close to its real customers_affected (see data/hartford_doe_oe417.js).
# "" for stormTrackSelect means uniform statewide placement (used for
# Snowtober, which real accounts describe as genuinely diffuse/statewide
# damage rather than a concentrated track).
STORMS = [
    ("isaias_2020", 20450, 4500, 264, "Isaias 2020"),
    # n_out corrected 19950->15500 following an authoritative customer-count
    # fix: PURA Docket 13-03-23's official decision gives Sandy's real CT
    # peak as 496,769, not the ~625,000 news-sourced estimate previously
    # used here (a ~26% overstatement) -- see data/hartford_doe_oe417.js.
    ("sandy_2012", 15500, 4000, 264, "Sandy 2012"),
    ("irene_2011", 21350, 3800, 288, "Irene 2011"),
    ("", 26050, 4800, 264, "Snowtober 2011"),
    ("may2018", 3980, 1000, 192, "May 2018"),
    ("jan2024", 1650, 500, 72, "Jan 2024"),
    ("dec2023", 2850, 700, 96, "Dec 2023"),
    ("henri_2021", 950, 300, 48, "Henri 2021"),
    # These last 2 are geographically-CONCENTRATED storms (a storm confined
    # to one corner of the state, is_localized_reports:true in
    # hartford_storm_tracks.js), unlike the 8 broad/statewide-track storms
    # above. Originally both badly missed (July 2026 ratio 0.57, Aug 2020
    # ratio 0.79) once workloadSlowdownMult existed, because that multiplier
    # was tuned only on the 8 broad storms and applied uniformly by customer
    # count alone. Diagnosed by forcing the multiplier to 1x in isolation:
    # both storms' BASE dispatch/ramp/workday mechanics alone already land
    # at real/sim 1.18-1.25 -- as good a fit as the broad storms get WITH
    # the multiplier. Fixed by gating workloadSlowdownMult on
    # storm.isLocalized (see planRestoration() in 03_grid_simulation.html):
    # concentrated storms skip it entirely now. (May 2018 above is ALSO
    # concentrated damage but doesn't use is_localized_reports -- it's
    # placed via the real HRRR grid, not synthetic town-centroid decay --
    # and correctly keeps getting the multiplier, since its gap looks like
    # tornado/derecho repair-severity complexity, a different mechanism.)
    # real_h refined 96->108h 2026-07-12: user-flagged discrepancy led to
    # re-verifying primary sources, which traced an early "~95k peak" claim
    # to a superseded day-1 snapshot and a "1-2 weeks" claim to a debris-
    # cleanup quote (not power restoration) -- see data/hartford_doe_oe417.js.
    ("ct_july2026_severe_tstorm", 6000, 702, 108, "July 2026 T-storm"),
    ("ct_aug2020_tornado", 1800, 380, 96, "Aug 2020 Tornado"),
    # LOWER CONFIDENCE than the entries above: real, sourced peak customer
    # count (~26,800, Eversource press release + live news) and a same-day
    # partial-restoration snapshot, but duration_h (72) and crew count (300,
    # used here) are interpolated from Henri 2021 (closest real neighbor by
    # customer count), not directly sourced -- see the notes on this entry
    # in data/hartford_doe_oe417.js. Broad nor'easter (not is_localized_
    # reports), so uses uniform placement like Snowtober. Crew count barely
    # moves sim_h here (48-49.5h across 250-350 crews tested) -- this storm
    # isn't crew-constrained at this scale, so the ratio below reflects
    # uncertainty in the real duration estimate more than a model gap.
    ("", 900, 300, 72, "March 2023 Nor'easter"),
    # Second real tornado/derecho-type event (NWS-confirmed serial derecho,
    # 2020-10-07), placed via the real HRRR grid + real NCEI storm reports
    # like May 2018, NOT synthetic town-centroid decay -- added specifically
    # to check whether May 2018's gap (needs MORE workloadSlowdownMult even
    # with the full multiplier applied) is a general pattern for HRRR-placed
    # severe convective storms, or specific to May 2018 itself. Real wind
    # data resolves this cleanly: this derecho's confirmed reports top out
    # at 69mph (0 outages cross the model's 70mph severity-repair threshold
    # -- straight-line wind damage, no confirmed tornadoes), vs May 2018's
    # real reports up to 100mph. It calibrates well with the standard
    # multiplier (ratio ~1.20, base-mechanics-alone ratio ~1.93 -- i.e. it
    # NEEDS the multiplier and gets a good fit from it, unlike May 2018
    # which still falls short even with it). Supports the theory that May
    # 2018's residual gap is tornado-severity-specific, not a broader
    # "severe convective storms need more slowdown" pattern. (Duration_h/
    # crews for this entry are themselves interpolated, not directly
    # sourced -- see data/hartford_doe_oe417.js -- so treat the exact ratio
    # loosely; the wind-severity comparison above doesn't depend on that
    # estimate.)
    ("oct2020_derecho", 2800, 700, 96, "Oct 2020 Derecho"),
    # A real, small-scale, TORNADO-ONLY event -- unlike every storm above,
    # this one carries no derecho/complex classification at all. Real NCEI
    # report confirms a 78kt (~90mph) tornado at Merrow/Coventry, cleanly
    # separated from 3 concurrent ordinary (50-52kt) thunderstorm-wind
    # reports elsewhere -- see hartford_storm_tracks.js's
    # "ct_sep2019_tornado" entry. Peak customers (2,900) real/sourced; by
    # far the smallest storm in this dataset (next is Calvin at 15,000).
    # 22/80 outages (27.5%) cross the severity threshold, max wind ~89mph
    # -- essentially matches the real ~90mph survey figure. duration_h (24)
    # and crews (60) are NOT sourced (no restoration timeline or crew count
    # found for an event this small/brief) -- so the ratio below is not a
    # meaningful validation signal either way; the wind-severity match
    # above is the useful, sourced part of this addition.
    ("ct_sep2019_tornado", 80, 60, 24, "Sep 2019 Tornado"),
    # Real, well-documented broad windstorm (not tornado/derecho). Higher
    # confidence than the last few additions: both crew count (1,100+) and
    # a restoration-complete date are directly sourced from an Eversource
    # press release, not interpolated. Real duration is "99% restored" by
    # 72h, not literally 100%, so a slightly-sub-1.0 ratio here is expected
    # rather than a miss.
    ("", 3900, 1100, 72, "Dec 2022 Windstorm"),
    # Real "bomb cyclone" nor'easter, 2019-10-16 overnight into 10-17 (set
    # October low-pressure records in Boston/Providence/Portland). Peak
    # ~45,200 (41,000 Eversource + 4,200 UI) sourced from live news at the
    # time; crew count (400) is interpolated between Henri 2021 and Jan
    # 2024, not sourced. Broad statewide system, uniform placement.
    ("", 1500, 400, 60, "Oct 2019 Bomb Cyclone"),
    # Remnants of Hurricane Ida, 2021-09-02 -- a genuinely different damage
    # mechanism (historic flash flooding, not wind/tree) from every other
    # storm in this dataset. Peak (~20,000) is real/sourced; duration (48h)
    # and crews (300) are interpolated directly from Henri 2021 (23,000
    # cust, nearly identical peak), not independently sourced.
    ("", 650, 300, 48, "Sep 2021 Ida Flooding"),
    # Real rain/windstorm, 2025-12-19. Peak (~89,200) estimated from a
    # restored+remaining snapshot ~30h post-storm; crews (700) interpolated
    # from Dec 2023 (near-identical peak). duration_h (72) extends past the
    # article's literal "substantially complete ~54h" milestone for the
    # true last-customer tail, same pattern as the July 2026 entry.
    ("", 2950, 700, 72, "Dec 2025 Windstorm"),
]


def main() -> None:
    script = _extract_script()
    data_inject = _load_data_inject()
    land_boundary = json.loads((DATA / "connecticut_land_boundary.json").read_text(encoding="utf-8"))
    land_geo = land_boundary[0]["geojson"]

    print(f"{'Storm':<16} {'N':>7} {'M':>6} {'RealH':>7} {'SimH':>8} {'Ratio':>7}")
    for track, n_out, m_crew, real_h, label in STORMS:
        sim_h, total_cust, log_tail = run_storm(script, data_inject, land_geo, track, n_out, m_crew)
        if sim_h is None:
            print(f"{label:<16} {n_out:>7} {m_crew:>6} {real_h:>7}    ERROR")
            print("  log:", log_tail)
            continue
        ratio = real_h / sim_h if sim_h else float("nan")
        print(f"{label:<16} {n_out:>7} {m_crew:>6} {real_h:>7} {sim_h:>8.1f} {ratio:>7.2f}")


if __name__ == "__main__":
    main()
