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
    ("sandy_2012", 19950, 4000, 264, "Sandy 2012"),
    ("irene_2011", 21350, 3800, 288, "Irene 2011"),
    ("", 26050, 4800, 264, "Snowtober 2011"),
    ("may2018", 3980, 1000, 192, "May 2018"),
    ("jan2024", 1650, 500, 72, "Jan 2024"),
    ("dec2023", 2850, 700, 96, "Dec 2023"),
    ("henri_2021", 950, 300, 48, "Henri 2021"),
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
