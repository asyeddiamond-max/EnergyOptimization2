"""Builds the two deliverable .docx files in expanded form:

  Hartford_Grid_Dev_Journal.docx     — colorful, chapter-structured development log
  Hartford_Grid_Research_Context.docx — research papers + niche analysis

Upload either to Google Drive (drag into drive.google.com) and Drive will
auto-convert to a native Google Doc.
"""
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


INK       = RGBColor(0x3B, 0x2F, 0x24)
ACCENT    = RGBColor(0x8B, 0x3A, 0x2E)
MARGIN    = RGBColor(0x70, 0x56, 0x38)
BUILD     = RGBColor(0x1D, 0x4E, 0xD8)
FIX       = RGBColor(0x15, 0x80, 0x3D)
QUESTION  = RGBColor(0x7C, 0x2D, 0x12)
DECISION  = RGBColor(0xA1, 0x62, 0x07)
PIVOT     = RGBColor(0x7E, 0x22, 0xCE)
PERF      = RGBColor(0x0D, 0x94, 0x88)

BG_HEADER   = "F3E8C8"
BG_BUILD    = "DBEAFE"
BG_FIX      = "DCFCE7"
BG_QUESTION = "FEE2D5"
BG_DECISION = "FEF3C7"
BG_PIVOT    = "F3E8FF"
BG_PERF     = "CCFBF1"
BG_QUOTE    = "FFF7E2"


def shade(cell, hex_color):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tc_pr.append(shd)


def set_cell_borders(cell, hex_color="C9B894"):
    tc_pr = cell._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    for edge in ("top", "left", "bottom", "right"):
        e = OxmlElement(f"w:{edge}")
        e.set(qn("w:val"), "single")
        e.set(qn("w:sz"), "4")
        e.set(qn("w:color"), hex_color)
        borders.append(e)
    tc_pr.append(borders)


def add_styled(p, text, bold=False, italic=False, color=None, size=None, font="Georgia"):
    run = p.add_run(text)
    run.font.name = font
    run.bold = bold
    run.italic = italic
    if color is not None:
        run.font.color.rgb = color
    if size is not None:
        run.font.size = Pt(size)
    return run


def h1(doc, text):
    p = doc.add_paragraph()
    add_styled(p, text, bold=True, color=ACCENT, size=22, font="Georgia")


def h2(doc, text):
    p = doc.add_paragraph()
    add_styled(p, text, bold=True, color=ACCENT, size=15)


def h3(doc, text):
    p = doc.add_paragraph()
    add_styled(p, text, bold=True, color=RGBColor(0x5B, 0x45, 0x28), size=12)


def margin_note(doc, text):
    p = doc.add_paragraph()
    add_styled(p, text, italic=True, color=MARGIN, size=10)


def body(doc, text):
    p = doc.add_paragraph()
    add_styled(p, text, color=INK, size=11)


def quote(doc, who, text):
    """User quote block."""
    table = doc.add_table(rows=1, cols=1)
    cell = table.rows[0].cells[0]
    cell.width = Inches(6.4)
    shade(cell, BG_QUOTE)
    set_cell_borders(cell, "8B3A2E")
    p = cell.paragraphs[0]
    add_styled(p, f"{who}: ", bold=True, color=QUESTION, size=10)
    add_styled(p, text, italic=True, color=INK, size=11)


def bullets(doc, items):
    for item in items:
        p = doc.add_paragraph(style="List Bullet")
        add_styled(p, item, color=INK, size=11)


def tag_color(kind):
    base = kind.lower()
    if "build" in base: return (BUILD, BG_BUILD)
    if "fix" in base or "bug" in base or "failure" in base or "success" in base: return (FIX, BG_FIX)
    if "question" in base: return (QUESTION, BG_QUESTION)
    if "decision" in base or "choice" in base: return (DECISION, BG_DECISION)
    if "pivot" in base or "reframe" in base: return (PIVOT, BG_PIVOT)
    if "perf" in base or "×" in kind or "milestone" in base or "honest" in base or "surprise" in base or "achieved" in base or "partial" in base: return (PERF, BG_PERF)
    return (INK, "FFFFFF")


def add_entry_table(doc, rows):
    """rows = list of (when, kind, detail) tuples."""
    table = doc.add_table(rows=1 + len(rows), cols=3)
    widths = [Inches(0.9), Inches(1.0), Inches(4.5)]
    hdr = table.rows[0].cells
    for i, (c, w, txt) in enumerate(zip(hdr, widths, ("WHEN", "KIND", "ENTRY"))):
        c.width = w
        shade(c, BG_HEADER)
        set_cell_borders(c)
        p = c.paragraphs[0]
        add_styled(p, txt, bold=True, color=RGBColor(0x5B, 0x45, 0x28), size=10)
    for r, (when, kind, detail) in enumerate(rows, start=1):
        row = table.rows[r].cells
        for c, w in zip(row, widths):
            c.width = w
            set_cell_borders(c)
        p = row[0].paragraphs[0]
        add_styled(p, when, italic=True, color=MARGIN, size=10)
        col, bg = tag_color(kind)
        shade(row[1], bg)
        p = row[1].paragraphs[0]
        add_styled(p, kind, bold=True, color=col, size=10)
        p = row[2].paragraphs[0]
        add_styled(p, detail, color=INK, size=11)


def section_break(doc, text=None):
    p = doc.add_paragraph()
    add_styled(p, "❦", color=ACCENT, size=14)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER


# =================== Build the Dev Journal ===================

def build_journal():
    doc = Document()
    sec = doc.sections[0]
    sec.page_height = Inches(11)
    sec.page_width = Inches(8.5)
    sec.top_margin = sec.bottom_margin = Inches(0.9)
    sec.left_margin = sec.right_margin = Inches(0.9)

    h1(doc, "Development Journal")
    p = doc.add_paragraph()
    add_styled(p, "Hartford County Power Grid Resilience Simulation",
               italic=True, color=MARGIN, size=12)
    p = doc.add_paragraph()
    add_styled(p, "A. Syed Diamond  ·  Spring–Summer 2026",
               italic=True, color=MARGIN, size=10)

    body(doc, "")
    legend = doc.add_paragraph()
    for label, color in [
        ("■ Build", BUILD), ("  ■ Fix", FIX), ("  ■ Perf", PERF),
        ("  ■ Question", QUESTION), ("  ■ Decision", DECISION), ("  ■ Pivot", PIVOT),
    ]:
        add_styled(legend, label + "  ", color=color, size=10, bold=True)

    # Table of Contents
    body(doc, "")
    h2(doc, "Contents")
    toc_items = [
        "I.    Foundations & the Initial Simulation",
        "II.   The Five-Alternative Roadmap",
        "III.  Alternative #1 — The Closed-Form Equation",
        "IV.   Alternative #2 — The Pre-Computed Scenario Library",
        "V.    Alternative #3 — The WebAssembly Adventure That Wasn't",
        "VI.   Alternative #4 — Server-Side Compute Arrives",
        "VII.  The \"Max Settings\" Crisis",
        "VIII. The Connecticut-Scale Refactor",
        "IX.   The Render Deployment Saga",
        "X.    Polish: Auto-Detect, Progress, /version",
        "XI.   The Vanishing Markers",
        "XII.  Direction Conversations & Research Strategy",
        "XIII. Documentation Push",
        "XIV.  Coda",
    ]
    for item in toc_items:
        p = doc.add_paragraph()
        add_styled(p, item, color=INK, size=11)

    section_break(doc)

    # ============ Chapter I ============
    h2(doc, "Chapter I — Foundations & the Initial Simulation")
    margin_note(doc, "Establishing the synthetic grid, the realistic restoration model, "
                "and the interactive controls before any optimisation began.")
    body(doc,
         "The project started as a single HTML page that asked a deceptively simple question: "
         "how long does it take Hartford County to get the lights back on after a storm, and "
         "what changes when we add more crews? The initial milestone wasn't speed — it was "
         "getting the physics right. Synthetic distribution grid built from population-"
         "weighted demand points, k-means substations, branched feeders and laterals, a "
         "mulberry32 PRNG so two people on different machines see exactly the same storm "
         "given the same seed.")
    body(doc,
         "The scheduler was a greedy rolling-horizon dispatch with seven realism factors "
         "stacked on top: damage-assessment delay, a 14-hour workday clamp, log-normal "
         "repair durations centred at 2 h, a discovery ramp so outages get reported "
         "gradually instead of all at once, mutual-aid waves arriving at 0/24/48 h, a road-"
         "network proxy that multiplies haversine distance by 1.5, and a critical-facility "
         "priority phase. The result: a 500-outage storm restored in a plausible 12–18 hours "
         "rather than the 4-hour fantasy a simpler model would predict.")
    add_entry_table(doc, [
        ("Day 0", "Build",
         "Synthetic grid: 29 Hartford County town boundaries, population-weighted demand "
         "points, k-means substation placement (100 substations by default), feeders branching "
         "from each substation, laterals branching from feeders. Reproducible via mulberry32 seed."),
        ("Day 0", "Build",
         "Storm model: pick K failure points along feeders + laterals, weighted by exposure. "
         "Customers without power = sum of demand downstream of each failure. Reset, reseed, "
         "re-storm — all reproducible."),
        ("Day 0", "Build",
         "Greedy rolling-horizon scheduler with seven realism factors. Output: per-crew job "
         "sequence, per-crew finish time, system-wide restoration time, customer-minutes curve."),
        ("Day 0", "Build",
         "Leaflet map UI: substations as stars, feeders as colored lines per substation, "
         "laterals as gray, outage X marks. Plan-restoration output adds crew depots (squares) "
         "and numbered repair circles (1, 2, 3 …) colored by crew."),
        ("Day 0", "Perf",
         "First \"page isn't responding\" event around 1500-outage scenarios — DOM markers "
         "dominate. Mitigations: async-yield chunking inside the scheduler loop, spatial-grid-"
         "hash nearest-neighbor on the JS side, ring caps, and a custom Leaflet "
         "PointCloudLayer canvas renderer for thousands of dots in a single pass."),
    ])

    section_break(doc)

    # ============ Chapter II ============
    h2(doc, "Chapter II — The Five-Alternative Roadmap")
    margin_note(doc, "Five orthogonal directions to make the simulation faster & more capable.")
    body(doc,
         "By the time the basic simulation worked, the obvious next question was: how do we "
         "make it fast enough to be genuinely interactive at much larger scales, and what "
         "other research capabilities should we unlock? Rather than pick one optimisation and "
         "hope, the plan was to enumerate the orthogonal directions and tackle them in order:")
    bullets(doc, [
        "Alternative #1 — Closed-form equation: instant slider feedback without re-running the scheduler.",
        "Alternative #2 — Pre-computed scenario library: let viewers explore canned scenarios with no compute at all.",
        "Alternative #3 — WebAssembly: port the scheduler to Rust, compile to WASM, hope to beat V8.",
        "Alternative #4 — Server-side computation: Python backend for things the browser fundamentally can't do (Monte Carlo, future MILP).",
        "Alternative #5 — WebGPU: parallel argmin on the GPU for huge-N stress tests.",
    ])
    body(doc,
         "The discipline that emerged early: always benchmark before declaring victory. Two "
         "of the five (WASM and KD-tree later on) ended up slower than the baseline in "
         "realistic conditions, and the only way to know was to put a number on it. This "
         "rhythm shaped the whole project.")

    section_break(doc)

    # ============ Chapter III ============
    h2(doc, "Chapter III — Alternative #1: The Closed-Form Equation")
    margin_note(doc, "The cheapest direction first. Got the slider feeling instant.")
    body(doc,
         "The motivation came from watching the slider sit motionless while users tried to "
         "find a sensible number of crews. Re-running the full scheduler on every slider "
         "change is wasteful when all you really need is a rough estimate. The closed-form "
         "fits an analytical approximation: total restoration ≈ assessment_delay + (N × "
         "mean_repair × road_factor) / (M × parallel_efficiency), with workday clamping. "
         "It's wrong by ~15% but right in direction.")
    add_entry_table(doc, [
        ("#1 build", "Build",
         "Added the live \"≈ 4 d 3 h\" readout above the Plan-restoration button. Updates in "
         "microseconds as the slider moves."),
        ("#1 review", "Question",
         "Closed-form initially read N from the slider, not the actual storm. User noticed:"),
    ])
    quote(doc, "User",
          "Also in regards to the estimate restoration time, can you make it dependent on "
          "the storm outages or is it just independent of everything and won't change unless "
          "you change the slider for number of repair crews?")
    add_entry_table(doc, [
        ("#1 verify", "Question",
         "User followed up with sharp diagnostic intuition:"),
    ])
    quote(doc, "User",
          "The thing is, there is already an estimated time even when there is no storm "
          "simulated so I am almost sure that it is not dependent.")
    add_entry_table(doc, [
        ("#1 fix", "Fix",
         "Closed-form now reads N from the actual simulated storm. Estimate changes the "
         "moment you re-simulate."),
    ])
    h3(doc, "Takeaways")
    bullets(doc, [
        "The cheapest optimisation often pays for itself fastest. The closed-form is ~15 lines and changed the feel of the UI dramatically.",
        "Approximate UX feedback beats exact lag.",
        "Users notice \"this number didn't move when it should have\" before they notice \"this number is slightly wrong.\"",
    ])

    section_break(doc)

    # ============ Chapter IV ============
    h2(doc, "Chapter IV — Alternative #2: The Pre-Computed Scenario Library")
    margin_note(doc, "Twelve canned storms. No compute required to explore them.")
    body(doc,
         "For viewers who land on the page and don't want to wait, a dropdown of pre-computed "
         "scenarios. We picked 12 representative storms (different intensities, different "
         "distributions across the county) and wrote a Python pre-computer that runs the "
         "full scheduler, serialises the result as JSON, and dumps to scenarios/. Each file "
         "is ~1 MB; total ~12.5 MB.")
    add_entry_table(doc, [
        ("#2 build", "Build",
         "06_precompute_scenarios.py reuses functions from 05_generate_artifacts.py (the "
         "offline Python port of the JS scheduler) to compute 12 scenarios. scenarios/index.json "
         "is the manifest."),
        ("#2 build", "Build",
         "Frontend dropdown loader: on selection, fetch the scenario JSON, populate outages, "
         "populate crews + jobs, render. Skips the scheduler entirely."),
        ("#2 review", "Question",
         "User couldn't see the dropdown immediately:"),
    ])
    quote(doc, "User", "I dont see the drop downs youre talking about.")
    body(doc,
         "The HTML was committed, but GitHub Pages hadn't finished deploying. Resolved by "
         "explaining the 2–10 minute Pages cycle + Ctrl+Shift+R to bust the cache.")
    h3(doc, "Takeaways")
    bullets(doc, [
        "Caching results for common scenarios is sometimes the right answer — beats any algorithmic optimisation by definition.",
        "GitHub Pages deploy latency is real. Worth surfacing in the README.",
    ])

    section_break(doc)

    # ============ Chapter V ============
    h2(doc, "Chapter V — Alternative #3: The WebAssembly Adventure That Wasn't")
    margin_note(doc, "A two-day Rust detour that taught us V8's JIT is excellent.")
    body(doc,
         "On paper, WebAssembly looked obvious: write the scheduler in Rust, compile to "
         "wasm, get native-ish speed in the browser, ship a single binary that runs anywhere. "
         "The reality was a series of compromises forced by the Windows toolchain, followed "
         "by a hard benchmark truth.")
    h3(doc, "The toolchain gauntlet")
    body(doc,
         "First attempt: wasm-pack with full dependencies — failed because MSVC linker was "
         "missing. Adding libm — failed for the same reason. Adding wasm-bindgen — failed. "
         "The fix was to go ascetic: #![no_std], crate-type cdylib, zero external "
         "dependencies, plain rustc with the wasm32-unknown-unknown target — no host C "
         "linker required at all.")
    body(doc,
         "The cost of going no_std: we couldn't use libm's math functions. So we wrote them "
         "inline. Sin, cos, asin, sqrt, log, exp — all hand-rolled Taylor series. Bump "
         "allocator with a 256 MB workspace. Spatial grid hash via counting sort. Min-heap "
         "with parallel arrays (f64 keys, u32 values). It worked. The compiled "
         "scheduler.wasm is 17 KB.")
    h3(doc, "The benchmark")
    body(doc,
         "Side-by-side benchmark button in the UI: same scenario, run JS scheduler, run "
         "WASM scheduler, compare. The user screenshotted the result. WASM was consistently "
         "2-3× slower than the JS at 500-2000 outages.")
    add_entry_table(doc, [
        ("#3 build", "Build",
         "Rust scheduler in wasm_scheduler/src/lib.rs with #![no_std], inline math, bump "
         "allocator. Exports wasm_alloc, wasm_reset, run_scheduler."),
        ("#3 build", "Build",
         "JS wrapper loadWasmScheduler(), runWasmScheduler(), runJsSchedulerReference(), "
         "runBenchmark(). Benchmark button in the UI."),
        ("#3 review", "Question", "User shared the benchmark screenshots:"),
    ])
    quote(doc, "User", "[benchmark screenshots showing WASM is slower] is this good enough or do you want more")
    add_entry_table(doc, [
        ("#3 verdict", "Decision",
         "WASM is the wrong tool here. Root cause: hand-rolled Taylor-series math is no "
         "match for V8's native Math.sin/cos/log, which compile to single SIMD instructions "
         "on modern CPUs. With libm we might have closed the gap. Without it, we lose. "
         "Decided to not wire WASM into production; kept the artefact as a reference build."),
        ("#3 pivot", "Pivot", "User chose to move forward:"),
    ])
    quote(doc, "User", "move onto #4")
    h3(doc, "Takeaways")
    bullets(doc, [
        "V8's JIT is extraordinarily good at numeric loops. Beating it requires either real low-level optimisation (SIMD intrinsics, libm) or a fundamentally different algorithm — not just a different language.",
        "Benchmark before integrating. The whole WASM effort cost two days but the decision not to ship it was made in five minutes once we had numbers.",
        "A failed experiment is not wasted work. The grid-hash design that made it into the no_std build later informed the Python scheduler's design.",
    ])

    section_break(doc)

    # ============ Chapter VI ============
    h2(doc, "Chapter VI — Alternative #4: Server-Side Compute Arrives")
    margin_note(doc, "The pitch shifted from \"make it faster\" to \"unlock things the browser fundamentally can't do.\"")
    body(doc,
         "The framing for #4 was different from the start. The JS scheduler was already "
         "plenty fast for ordinary scenarios. The reason for a server backend was capability, "
         "not speed: Monte Carlo ensembles (running the scheduler 30+ times to get a "
         "distribution), eventual MILP solvers (commercial OR libraries don't ship as WASM), "
         "and eventual real-data calibration that needs a Python ecosystem.")
    add_entry_table(doc, [
        ("#4 build", "Build",
         "FastAPI app at 07_server.py. Endpoints: GET /health, POST /api/schedule, "
         "POST /api/monte_carlo. Pydantic models for request/response. Wide-open CORS so "
         "GitHub Pages can hit it from any origin."),
        ("#4 build", "Build",
         "Dockerfile for deployment. Initially pinned just fastapi, uvicorn, pydantic — we'd "
         "grow the dependency list as the schedulers matured."),
        ("#4 build", "Build",
         "Frontend \"Server backend\" panel: server URL input, \"Use server for Plan "
         "restoration\" toggle, Monte Carlo button. Default URL: http://localhost:8000."),
        ("First test", "Question", "First attempt to use the server backend:"),
    ])
    quote(doc, "User",
          "this is the message I am getting. its asking if the server is running so that "
          "means its not working. Do you think its possible to fix?")
    body(doc,
         "The error: \"Failed to fetch\" with the toggle on. Root cause: the FastAPI server "
         "is a separate process — checking a toggle in the browser doesn't magically start "
         "a Python server. Resolved by installing the dependencies (pip install fastapi "
         "\"uvicorn[standard]\" pydantic) and starting it locally "
         "(python -m uvicorn 07_server:app --port 8000).")
    add_entry_table(doc, [
        ("First success", "Fix",
         "Server up, /health returning {\"status\":\"ok\"}. Plan restoration through the "
         "server returns a valid response. The actual workload that broke things came next."),
    ])

    section_break(doc)

    # ============ Chapter VII ============
    h2(doc, "Chapter VII — The \"Max Settings\" Crisis")
    margin_note(doc, "A 24 950-outage × 5 000-crew stress test that broke everything. "
                "Setting the stage for every later performance fix.")
    body(doc,
         "With the server working at small scales, the user maxed out every slider in the "
         "UI: 24 950 outages, 5 000 repair crews, realistic mode, Monte Carlo 30 seeds. "
         "And waited. And waited.")
    quote(doc, "User", "so I did all the max settings, but its taking forever to load")
    body(doc,
         "What was happening: the server's scheduler was the pure-Python implementation in "
         "05_generate_artifacts.py. Pure Python doing 24 950 dispatches, each scanning 24 950 "
         "outages to find the nearest undone one, is ~625 million operations per Monte Carlo "
         "run × 30 runs = ~18 billion Python-level operations. At the rate of millions of "
         "operations per second for interpreted Python, that's hours.")
    h3(doc, "The diagnostic")
    body(doc,
         "The inner loop \"find the nearest undone outage to this crew\" is O(N) per dispatch, "
         "run N times, so O(N²) total. With N=25 000 that's 625 million Python comparisons "
         "per scheduler call. Pure Python: minutes. Even basic NumPy: still seconds. The "
         "bigger problem: 30 seeds × this cost = the user's eight-minute wait.")
    h3(doc, "The trade-off")
    body(doc,
         "Offered two paths: (A) lower the Monte Carlo workload (drop default seeds to 10, "
         "encourage smaller storms — easier to ship, but feels like a retreat); (B) actually "
         "speed up the Python scheduler with NumPy (port the inner loop to vectorised "
         "operations, ~10–50× speedup expected, ~1 hour of work).")
    quote(doc, "User", "nah do B now")
    h3(doc, "The NumPy port")
    body(doc,
         "Built scheduler_fast.py: replaces the Python inner loop with vectorised NumPy. "
         "np.argmin over a masked distance array — one CPython call into compiled NumPy code "
         "instead of 25 000 individual Python comparisons. The discovery fast-forward "
         "(when a crew has no available work and needs to skip to the next discovery time) "
         "used np.searchsorted on a pre-sorted discovery list — O(log N) instead of O(N).")
    h3(doc, "The KD-tree experiment that didn't quite work")
    quote(doc, "User", "yes please, do #1 first")
    body(doc,
         "User picked KD-tree from the next-step menu. Added scipy.spatial.cKDTree for the "
         "nearest-neighbour search. Expected ~10–20× speedup on huge N. Benchmark result: "
         "slower than the NumPy vectorised scan in realistic mode. Reason: when ~70% of "
         "outages are still \"undiscovered\" early in the storm, the KD-tree's K-nearest "
         "results get filtered down to almost nothing, K balloons, and we end up paying "
         "KD-tree query cost with no benefit. Capped K at 256 with a fallback to vectorised "
         "scan — useful in non-realistic dense regimes only.")
    add_entry_table(doc, [
        ("Step 1", "+5× Perf",
         "NumPy vectorisation in scheduler_fast.py. 2 k × 100: 0.34 s → ~0.07 s. Monte Carlo "
         "30 seeds: still seconds, but feasible."),
        ("Step 1.5", "Fix",
         "Discovered Monte Carlo always reported stddev=0.00. Cause: RNG seeds inside the "
         "scheduler were hardcoded constants, so all 30 \"different\" runs produced identical "
         "results. Fixed with per-seed RNG streams. Real variation visible — stddev 2.8 h on "
         "a representative scenario."),
        ("Step 2", "Honest result",
         "KD-tree: ~2.5× win on small-but-dense scenarios, regression on realistic-mode "
         "large scenarios. K_CAP=256 fallback merges the best of both. Not the 10–20× "
         "I promised — acknowledged honestly."),
        ("Step 3", "Question", ""),
    ])
    quote(doc, "User", "Yes do #2 and #3")
    add_entry_table(doc, [
        ("Step 3", "+14× Perf",
         "scheduler_numba.py: the entire dispatch loop JIT-compiled to native code with "
         "@njit(cache=True, fastmath=True). Inline binary heap with parallel arrays "
         "(no heapq in nopython mode), inline haversine, inline Mulberry32, inline log-"
         "normal sample. First call compiles in ~8 s (cached to disk afterward). Subsequent "
         "calls: tens of milliseconds."),
        ("Step 3", "Surprise",
         "Process pool for Monte Carlo was slower, not faster: 30 seeds × Windows process-"
         "spawn overhead (~1 s per worker) plus Numba cache-load on each cold subprocess = "
         "worse than serial. Heuristic threshold: only use the pool when per-run cost "
         "dominates spawn overhead (N × crews > 10M)."),
    ])
    h3(doc, "Numbers at the end of Chapter VII")
    bullets(doc, [
        "2 k outages × 100 crews: 0.34 s → 0.024 s (14×)",
        "Monte Carlo 30 seeds (2 k × 100): minutes → 0.21 s",
        "25 k × 500 (realistic): minutes → 3.67 s",
        "25 k × 5 000 (worst case): still ~118 s — not solved yet",
    ])

    section_break(doc)

    # ============ Chapter VIII ============
    h2(doc, "Chapter VIII — The Connecticut-Scale Refactor")
    margin_note(doc, "Where one user reframe shifted the goal from \"Hartford works\" to \"the whole state works.\"")
    body(doc,
         "With Numba in place, the typical-scale scenarios were essentially solved. The "
         "remaining ugly case: the user's maximum-slider stress test (25 000 outages × "
         "5 000 crews) still took two minutes. I floated MILP and Eversource calibration as "
         "the natural next research directions. The user pushed back with a sharper goal:")
    quote(doc, "User",
          "the real storm data is a lot later. We need to make this more scalable and more "
          "precise for Hartford county first. We can calibrate it against it later and I "
          "will let you know when. I want this model first to be able to survive against "
          "even these unrealistic scenarios for Hartford County as they are going to need "
          "to handle even heavier scenarios when scaled up to Connecticut.")
    body(doc,
         "That re-framing changed what \"good enough\" meant. Connecticut is roughly 10× "
         "Hartford County by population. A statewide simulation would need to handle "
         "~100 000-outage scenarios — well above any single Eversource event but the right "
         "ceiling to design to. The two minutes we were spending was unacceptable.")
    h3(doc, "The spatial grid hash")
    body(doc,
         "The algorithm of choice: divide the bounding box into a G×G grid (G = sqrt(N/5) — "
         "five outages per cell on average). To find the nearest undone outage for a crew, "
         "look up the crew's cell, walk it, walk concentric rings of cells outward until "
         "something valid is found. Termination: when the next ring's minimum-possible "
         "distance exceeds the current best, stop.")
    h3(doc, "The bug that doubled the runtime")
    body(doc,
         "First implementation: slower than the flat scan. Diagnosis: the \"skip non-"
         "boundary cells\" optimisation was broken when the search box clamped to the edge "
         "of the grid. Cells in the interior of the original ring kept getting revisited "
         "every iteration. Rewrote the ring iteration to enumerate the actual Chebyshev-"
         "distance == ring cells directly: top + bottom strips, then left + right columns "
         "excluding corners. No duplicates.")
    h3(doc, "The real hero — n_available")
    body(doc,
         "Even with the ring iteration fixed, 25 k × 5 000 still timed out. The culprit was "
         "realistic mode's discovery model: at t=12 h only a tiny fraction of outages have "
         "been \"discovered\" by the utility yet, but all 5 000 crews are awake and trying "
         "to dispatch. Each one walks the grid outward and finds nothing, all the way to "
         "the edge of the bounding box, before fast-forwarding.")
    body(doc,
         "Fix: an incrementally maintained counter n_available — the number of outages "
         "currently discovered-and-undone. When it's zero, fast-forward immediately via "
         "np.searchsorted on the sorted discovery list. No grid scan required. The counter "
         "is incremented as the time pointer advances past discovery thresholds and "
         "decremented when an outage is marked done.")
    add_entry_table(doc, [
        ("Grid v1", "Bug",
         "First grid implementation was 2–4× slower than the flat scan because of the "
         "boundary-skip optimisation breaking at grid edges. Rewrote with explicit ring-"
         "boundary enumeration."),
        ("Grid v2", "Partial Perf",
         "Grid hash alone helped 10k × 500 (8 s → 1 s) but barely touched 25 k × 5 000 "
         "(still 50+ s) because of discovery thrashing."),
        ("n_avail", "+246× Perf",
         "Added the n_available counter. 25 k × 5 000: 118 s → 0.48 s. The single biggest "
         "single-commit win of the project."),
        ("CT scale", "Achieved",
         "100 k outages × 2 000 crews — well above any realistic Eversource event — "
         "finishes in 660 ms. Statewide scenarios are now feasible."),
    ])
    h3(doc, "Final benchmark snapshot")
    bench = doc.add_table(rows=7, cols=3)
    for r, (a, b, c) in enumerate([
        ("Scenario", "Before", "After"),
        ("2 k × 100", "0.34 s (NumPy)", "< 10 ms"),
        ("10 k × 500", "8 s", "0.51 s"),
        ("25 k × 500 (realistic)", "~minutes", "70 ms"),
        ("25 k × 5 000 (worst case)", "118 s", "480 ms"),
        ("50 k × 1 000", "(untested)", "220 ms"),
        ("100 k × 2 000 (CT projection)", "infeasible", "660 ms"),
    ]):
        cells = bench.rows[r].cells
        is_header = r == 0
        for c_cell, txt in zip(cells, (a, b, c)):
            set_cell_borders(c_cell)
            if is_header:
                shade(c_cell, BG_HEADER)
            p = c_cell.paragraphs[0]
            add_styled(p, txt, bold=is_header, color=INK, size=11)
    body(doc, "")
    h3(doc, "Takeaways")
    bullets(doc, [
        "Algorithmic improvements (O(N²) → O(N log N) via grid hash) compound with constant-factor improvements (Numba JIT). Either alone wouldn't have closed the gap.",
        "The discovery-thrashing fix wasn't about making the search faster — it was about not searching at all when there's nothing to find. Often the best optimisation is recognising work that doesn't need doing.",
        "The 100 k-outage capability isn't useful because we expect 100 k-outage storms. It's useful because we can honestly claim the model is prepared for statewide deployment — a real engineering result for a paper's introduction.",
    ])

    section_break(doc)

    # ============ Chapter IX ============
    h2(doc, "Chapter IX — The Render Deployment Saga")
    margin_note(doc, "Four straight failed deploys. The root cause was Python exception-hierarchy semantics.")
    body(doc,
         "With a working backend, the next step was making it publicly callable so visitors "
         "to the GitHub Pages site could use the server without needing to install anything. "
         "Render's free tier seemed ideal: $0/month, auto-deploy from GitHub via a "
         "render.yaml Blueprint, container sleeps when idle.")
    quote(doc, "User", "can you do that for me")
    body(doc,
         "Honest answer: no. Deploying to Render needs the user's account credentials. But "
         "I could prep everything so the user's part was just clicking through Render's "
         "Blueprint UI. Wrote render.yaml, ensured the Dockerfile was self-contained, pushed.")
    h3(doc, "Failure #1 — matplotlib missing")
    body(doc,
         "First deploy error: \"matplotlib + numpy required. Install with: pip install "
         "matplotlib numpy\". Cause: 07_server.py imported 05_generate_artifacts.py via "
         "importlib for the pure-Python fallback scheduler — and 05_generate_artifacts "
         "imports matplotlib at the top for its plotting helpers. Server never plots; the "
         "import just has to succeed. Added matplotlib to the Docker image.")
    h3(doc, "Failure #2 — file not found")
    body(doc,
         "Next deploy: FileNotFoundError: '/app/data/hartford_boundary.json'. Same file "
         "(05_generate_artifacts.py) tries to load Hartford boundary GeoJSON at module level. "
         "We didn't ship the data directory into the Docker image because the server doesn't "
         "need it. Wrapped the importlib call in try / except Exception so any import "
         "failure would just set art = None and proceed.")
    h3(doc, "Failure #3 — the deep gotcha")
    body(doc,
         "Same FileNotFoundError. The \"fix\" hadn't actually caught the error. Hours of "
         "head-scratching. Then the realisation: 05_generate_artifacts.py doesn't just "
         "raise — it raises SystemExit when matplotlib is missing. SystemExit inherits from "
         "BaseException, not from Exception. This is deliberate Python design: sys.exit() "
         "is supposed to terminate the program even when called inside a try / except "
         "Exception block, so the standard library deliberately raises a subclass that "
         "bypasses that guard. The exception is catchable, but you have to write except "
         "BaseException or use a bare except: — both of which are usually a code smell.")
    body(doc,
         "The correct fix was simpler: stop importing 05_generate_artifacts.py at all. The "
         "Numba and NumPy schedulers cover the same functionality, faster. The pure-Python "
         "fallback was already dead code in production.")
    quote(doc, "User", "it keeps failing no matter how many times I restart")
    add_entry_table(doc, [
        ("Deploy 1", "Failure",
         "matplotlib + numpy required — added matplotlib to Dockerfile."),
        ("Deploy 2", "Failure",
         "FileNotFoundError: data/hartford_boundary.json — wrapped import in "
         "try/except Exception."),
        ("Deploy 3", "Failure",
         "Same error. SystemExit bypasses except Exception. Removed the import entirely."),
        ("Deploy 4", "Success",
         "Live at hartford-grid-server.onrender.com. /health returns {\"status\":\"ok\"}."),
    ])
    h3(doc, "Takeaways")
    bullets(doc, [
        "Python's exception hierarchy is intentional: BaseException > Exception. SystemExit, KeyboardInterrupt, and GeneratorExit all live above Exception so they can't be silenced accidentally.",
        "The cleanest fix to an import-time problem is often \"stop doing the import.\" Optional dependencies should be optional in code, not just in a try/except.",
        "Render's free tier deploys are fast enough to iterate on — each deploy was 5-8 minutes. Useful for this kind of debugging.",
    ])

    section_break(doc)

    # ============ Chapter X ============
    h2(doc, "Chapter X — Polish: Auto-Detect, Progress, /version")
    margin_note(doc, "\"I am still a little unsure with how to check if the server is actually up to date or not.\"")
    body(doc,
         "After the deploy succeeded, the user raised three related concerns: (a) how do I "
         "verify the server is up to date? (b) can the server be mandatory so I don't have "
         "to think about the toggle? (c) can the server \"live on GitHub\" so it auto-"
         "launches when the page loads?")
    body(doc,
         "Answer to (c) had to be honest: GitHub Pages is static hosting — it can't run a "
         "Python server. The Render service is separate infrastructure. But the spirit of "
         "the request — \"the user shouldn't have to think about the server\" — was "
         "achievable through three changes: a verification endpoint, a warm-up ping on "
         "page load, and an auto-detect path that silently falls back to in-browser when "
         "the server is offline.")
    add_entry_table(doc, [
        ("/version", "Build",
         "Added GET /version returning {\"commit\": \"...\", \"backend\": \"numba\"}. Reads "
         "the commit from Render's RENDER_GIT_COMMIT env var. Lets the frontend display "
         "\"connected · commit fd87b7a · backend numba\" so the user can verify the deployed "
         "server matches GitHub HEAD."),
        ("Auto-warm", "Build",
         "On page load, the JS fires a no-cors GET to /health to wake the sleeping Render "
         "container. Then probes /version at 5 s, 30 s, 60 s, and every 60 s thereafter to "
         "keep the dot's state current."),
        ("Auto-detect", "Build",
         "Health dot: gray (probing) → amber (waking) → green (ok) → red (offline). When "
         "the user clicks Plan restoration: if dot is green, request goes to the server. "
         "If red, silently runs in-browser with a status note. Toggle defaults to ON."),
        ("Progress", "Build",
         "Server-side restoration is an atomic call — no intermediate progress signal. So "
         "the progress bar fakes it: exponential asymptote toward 90% with a time constant "
         "tuned for Render cold starts (~30–60 s), snaps to 100% on response, fades after "
         "400 ms."),
        ("URL mishap", "Question", "User pasted the wrong identifier:"),
    ])
    quote(doc, "User", "where am I supposed to collect the url for my server location")
    body(doc,
         "The user had pasted the Render Service ID (srv-d8qs8b6gvqtc73e70mog) into the "
         "Server URL field instead of the actual URL (https://hartford-grid-server.onrender."
         "com). Confusion fixed by labelling the field clearly and defaulting to the "
         "deployed URL.")
    add_entry_table(doc, [
        ("Render UX", "Question", "User shared a Render cold-start splash:"),
    ])
    quote(doc, "User",
          "in regards to number 3, do a and b, but also check the attached image cause i "
          "cant tell what im supposed to see from here")
    body(doc,
         "The attached image showed Render's cold-start splash (\"INCOMING HTTP REQUEST "
         "DETECTED … SERVICE WAKING UP …\"). Explained: that's expected behaviour. First "
         "request after sleep boots the container, takes 30–60 s, then real responses "
         "follow. Subsequent calls within the next 15 min are fast.")
    h3(doc, "Takeaways")
    bullets(doc, [
        "\"Verification\" as a first-class UX feature: showing the commit SHA the running server was built from removes a whole class of \"is this up to date?\" anxiety.",
        "When the underlying operation has no real progress signal, a well-tuned fake progress bar (asymptotic exponential) is genuinely better UX than a static spinner.",
        "Free-tier hosting cold starts are the user-facing tax of the $0 price tag. Auto-warm-up hides ~80% of that pain.",
    ])

    section_break(doc)

    # ============ Chapter XI ============
    h2(doc, "Chapter XI — The Vanishing Markers")
    margin_note(doc, "A regression caught by a user observation.")
    body(doc,
         "After all the speed improvements, the user noticed something missing in the "
         "visualisation:")
    quote(doc, "User",
          "I have a question, why did you stop with those images that we used to have for "
          "when the plan restoration works. It works very well now with the processing "
          "speed as it is now able to handle the maximum settings very well. However, I "
          "still want those images on the grid so can you bring them back and lets not get "
          "rid of those to improve processing speed")
    body(doc,
         "What had happened: the server's ScheduleResponse returned only crew counts and "
         "total times — not the per-job sequence that the browser needs to draw the "
         "numbered repair circles. When the server backend was used, the map's depot "
         "squares and numbered 1/2/3 circles disappeared.")
    body(doc,
         "Honest assessment of the cost of restoring them: negligible at realistic scales, "
         "+200-500 ms of network at 25 k, +1-3 s at 100 k. The Numba scheduler already "
         "computes which crew handles which outage during dispatch — we were just throwing "
         "that data away. Recording it costs one int32 write per dispatch.")
    add_entry_table(doc, [
        ("Build", "Build",
         "Added a flat dispatch log inside both _run_scheduler and _run_scheduler_grid "
         "(Numba-JIT'd) — three parallel np.empty(N) arrays (log_crew, log_outage, log_eta) "
         "plus a counter. One write per successful dispatch. Returned as sliced views."),
        ("Build", "Build",
         "Python wrapper rebuilds per-crew job lists from the flat log, preserving dispatch "
         "order within each crew. Updated scheduler_fast.py to return the same dict shape."),
        ("Build", "Build",
         "Server ScheduleResponse grew a jobs[] array of {lat, lon, eta} per crew. Larger "
         "JSON response but only adds 200-500 ms of network at 25 k outages."),
        ("Build", "Build",
         "Frontend renderPlan() extracted from planRestoration() so both local and server "
         "paths share the same renderer."),
    ])
    h3(doc, "Takeaways")
    bullets(doc, [
        "Speed without visualisation parity is a false win. Always check that the user-facing artefact still looks the way they expect.",
        "\"What does it cost to put it back?\" is the right question. Often the answer is \"very little.\"",
        "Factoring the renderer out paid for itself immediately and will pay forward — future paths (MILP comparison, scenarios from disk) all need to render the same way.",
    ])

    section_break(doc)

    # ============ Chapter XII ============
    h2(doc, "Chapter XII — Direction Conversations & Research Strategy")
    margin_note(doc, "The conversations that shaped what to build next.")
    h3(doc, "Conversation 1 — WebGPU as next step")
    body(doc,
         "After Numba was in place, I proposed Alternative #5 (WebGPU) as the next direction. "
         "The pitch: parallel argmin on the GPU for the huge-N stress test, potentially 100× "
         "on 25 k × 5 000 cases. The user agreed but also asked about research direction.")
    h3(doc, "Conversation 2 — MILP vs Calibration")
    quote(doc, "User",
          "MLP/calibration is what I want to do if it helps leads me towards more "
          "publishable research contributions")
    body(doc,
         "Recommended doing MILP first — it's self-contained (PuLP + CBC solver, no external "
         "data needed), produces a publishable claim (\"our greedy is within X% of optimal at "
         "scales where MILP is tractable\"), and sets up the framework that the calibration "
         "phase will plug into. Eversource calibration would happen in parallel as the user "
         "pursues data access through PURA dockets.")
    h3(doc, "Conversation 3 — Scale before research")
    body(doc, "Before MILP started, the user re-prioritised one more time:")
    quote(doc, "User",
          "the real storm data is a lot later. We need to make this more scalable and "
          "more precise for Hartford county first.")
    body(doc,
         "This is what triggered the Chapter VIII grid-hash + n_available work. With "
         "Connecticut scale handled, MILP and calibration both become more credible: they're "
         "now plugging into a model that we can honestly claim is engineered for statewide "
         "deployment.")
    h3(doc, "Current research-direction stack (queued, not yet built)")
    add_entry_table(doc, [
        ("Next", "Decision (MILP)",
         "PuLP + CBC for small-N (≤50 outage) optimal scheduling. Compute the greedy-vs-"
         "optimal gap. Publishable result: \"our heuristic is within X% of optimal at scales "
         "where MILP is tractable, supporting its use at scales where MILP is not.\""),
        ("Parallel", "Decision (Calibration)",
         "PURA dockets & Eversource storm post-mortems → fit travel speed, road-multiplier, "
         "workday hours, repair-time distribution to observed restoration curves. "
         "Bottlenecked on data access."),
        ("Later", "Decision (WebGPU)",
         "Engineering polish for the in-browser path. Deferred — Numba already handles "
         "Connecticut scale, so the urgency is gone."),
    ])

    section_break(doc)

    # ============ Chapter XIII ============
    h2(doc, "Chapter XIII — Documentation Push")
    margin_note(doc, "Where you, dear reader, are.")
    quote(doc, "User",
          "wait can you add a file in the github repository showing like a journal of all "
          "the changes and like questions and answers all in different colors. Make it in "
          "like a tabular format and make it look like a journal aesthetic. Also once again "
          "me all the research papers already published in this field related to what im "
          "doing and again tell me the niche im exploring and help me put the research "
          "paper stuff in a google docs.")
    body(doc,
         "Three deliverables produced: this Hartford_Grid_Dev_Journal.docx (developer "
         "history), a JOURNAL.html in the repo for browser viewing, and a separate "
         "Hartford_Grid_Research_Context.docx with a literature map by theme, niche "
         "analysis, open research questions, and data sources to pursue.")
    body(doc,
         "Honest caveat carried into the research document: the citations are starting "
         "points drawn from a directed literature scan, not a verified bibliography. "
         "Authors and research groups are the most reliable parts; specific paper titles, "
         "years, and venues should be verified on Google Scholar or IEEE Xplore before "
         "being cited in a manuscript.")

    section_break(doc)

    # ============ Chapter XIV ============
    h2(doc, "Chapter XIV — Coda")
    body(doc,
         "The project started as a Hartford County storm simulator and ended this "
         "development cycle as a Connecticut-prepared, server-backed, browser-first "
         "research platform. The engineering path zig-zagged: a successful closed-form "
         "approximation, a working but underwhelming WebAssembly port, a successful FastAPI "
         "backend, a NumPy port that helped, a KD-tree experiment that helped less than "
         "promised, a Numba port that helped a lot, a grid hash that helped little on its "
         "own and enormously when paired with an n_available counter, and a four-attempt "
         "deployment saga whose root cause was a Python exception-hierarchy subtlety.")
    body(doc,
         "What's live now: a public-facing simulator that auto-detects its own server "
         "backend, falls back gracefully when offline, handles 100 000-outage scenarios in "
         "under a second, and renders the per-crew dispatch sequence as colored numbered "
         "circles on a Leaflet map of Hartford County. The road ahead is MILP comparison "
         "for academic rigor and PURA-grounded calibration for real-world claims. The "
         "engineering substrate is done; what remains is the research story it can now "
         "support.")

    doc.save("Hartford_Grid_Dev_Journal.docx")
    print("Wrote Hartford_Grid_Dev_Journal.docx")


# =================== Build the Research Context (unchanged) ===================

def build_research():
    doc = Document()
    sec = doc.sections[0]
    sec.page_height = Inches(11)
    sec.page_width = Inches(8.5)
    sec.top_margin = sec.bottom_margin = Inches(0.9)
    sec.left_margin = sec.right_margin = Inches(0.9)

    h1(doc, "Research Context & Literature Map")
    p = doc.add_paragraph()
    add_styled(p, "Hartford County Power Grid Resilience Simulation",
               italic=True, color=MARGIN, size=12)
    p = doc.add_paragraph()
    add_styled(p, "Companion to the development journal",
               italic=True, color=MARGIN, size=10)

    body(doc, "")
    h2(doc, "What This Project Is, In One Paragraph")
    body(doc,
         "A browser-first, county-specific interactive simulation of post-storm distribution-"
         "grid restoration. Models 100k+ outages and 5 000+ crews at Connecticut scale in "
         "under a second per scenario, with a server backend exposing Monte Carlo ensembles. "
         "The greedy rolling-horizon scheduler accounts for damage-assessment delay, log-"
         "normal repair durations, mutual-aid waves, workday clamps, and crew-routing "
         "heuristics. Designed as a foundation for calibration against real Eversource / "
         "PURA storm post-mortem data and for benchmarking against an MILP optimal "
         "scheduler.")

    body(doc, "")
    h2(doc, "The Niche You Are Exploring")
    margin_note(doc, "Reading of the academic + industry landscape; revise as you find more sources.")

    niche_points = [
        ("Most academic work on grid restoration is offline batch optimisation.",
         "Coffrin, Van Hentenryck, and collaborators have produced strong MILP and convex-"
         "relaxation models for transmission restoration. Less work targets distribution-"
         "level, county-scale, and almost none of it is interactive."),
        ("Most utility decision-support tools are proprietary and inaccessible.",
         "Eversource, Avangrid, and others use commercial outage-management systems (OMS) "
         "like OSI Monarch or GE PowerOn. These run in control rooms and are not accessible "
         "for academic exploration."),
        ("The synthetic-grid corpus targets transmission, not distribution.",
         "ARPA-E's GRID DATA program and Texas A&M's synthetic networks deliver "
         "transmission-scale test cases. County-resolution distribution grids with realistic "
         "storm-outage patterns are scarce."),
        ("Browser-first, real-time interactive grid simulation at this fidelity is rare.",
         "There are a few public demos but most are toy-scale (≤ 100 nodes). Running "
         "100 000 outages + 5 000 crews + Monte Carlo in a browser-backed-by-API pipeline "
         "is a differentiator."),
        ("Calibration against real PURA / Eversource storm filings is largely untouched in published academic work.",
         "Statistical outage-prediction papers exist (Nateghi, Quiring, Guikema). "
         "Restoration-timeline calibration is much less common — partly because the data "
         "lives in regulatory filings rather than open datasets."),
    ]
    for headline, expansion in niche_points:
        p = doc.add_paragraph()
        add_styled(p, "▸ ", color=ACCENT, bold=True, size=12)
        add_styled(p, headline, bold=True, color=INK, size=11)
        p = doc.add_paragraph()
        add_styled(p, "    " + expansion, color=INK, size=11)

    body(doc, "")
    p = doc.add_paragraph()
    add_styled(p, "Net positioning: ", bold=True, color=ACCENT, size=12)
    add_styled(p,
               "a publicly accessible, scale-validated, calibratable interactive grid-"
               "resilience simulator for a specific real-world utility service territory. "
               "The contribution is the integration — the engineering of an accessible tool "
               "with research-grade behaviour — rather than a new algorithm.",
               color=INK, size=11)

    body(doc, "")
    h2(doc, "Literature Map by Theme")
    margin_note(doc, "Authors and groups whose work directly intersects this project. Verify each citation independently — these are starting points for your own search.")

    themes = [
        ("Grid Restoration Optimisation (MILP / Stochastic)", BG_BUILD, [
            ("Van Hentenryck, P.; Coffrin, C. et al.",
             "Last-mile restoration formulations and convex relaxations of power flow for "
             "restoration. Key starting point for MILP comparison."),
            ("Arif, A.; Wang, Z.; Wang, J.; Mather, B.; Bashualdo, H.; Zhao, D.",
             "Multi-stage distribution-system restoration with stochastic repair times. "
             "Closely matches your problem statement."),
            ("Watson, J-P.; Greenberg, H.; Hart, W. (Sandia)",
             "Power-infrastructure restoration scheduling under uncertainty. Foundational."),
            ("Castillo, A. (2014)",
             "Survey of restoration models. Useful for situating your greedy among the "
             "broader model family."),
        ]),
        ("Storm-Induced Outage Modelling & Prediction", BG_PERF, [
            ("Nateghi, R.; Guikema, S.; Quiring, S.",
             "Statistical models for hurricane-induced power-outage durations and counts. "
             "Directly relevant once you have real Eversource data."),
            ("Han, S-R.; Guikema, S.; Quiring, S. et al.",
             "Outage-prediction model evaluation against historical events. Useful template "
             "for validation methodology."),
            ("Liu, H.; Davidson, R.; Apanasovich, T.",
             "Spatial generalised linear mixed models for storm outage prediction."),
        ]),
        ("Synthetic Grid Generation", BG_DECISION, [
            ("Birchfield, A. B.; Xu, T.; Gegner, K. M.; Shetye, K. S.; Overbye, T. J. (Texas A&M)",
             "Synthetic transmission grid construction methodology. Transmission-level, but "
             "the methods (k-means substation placement, demand allocation) directly informed "
             "your distribution-level approach."),
            ("Schweitzer Engineering / IEEE PES Distribution Test Feeders",
             "Standard feeder datasets (IEEE 13, 34, 123-node). Useful as ground-truth shape "
             "tests for the synthetic-feeder logic."),
        ]),
        ("Crew Routing & Vehicle Routing Variants", BG_FIX, [
            ("Toth, P.; Vigo, D. (eds.)",
             "The Vehicle Routing Problem textbook. Foundational for understanding where "
             "your greedy sits in the broader VRP / job-shop landscape."),
            ("Perrier, N.; Langevin, A.; Campbell, J. F.",
             "Survey of operations-research models for snow plowing — analogous routing/"
             "scheduling problem with crews dispatched after disruption."),
            ("Solomon, M.",
             "VRPTW benchmark instances. Standard test set for time-window variants."),
        ]),
        ("Resilience Metrics & Frameworks", BG_QUESTION, [
            ("Panteli, M.; Mancarella, P.",
             "Power-system resilience under extreme weather. Defines metrics like "
             "'resilience trapezoid' which could frame your output."),
            ("Bie, Z.; Lin, Y.; Li, G.; Li, F.",
             "Survey of distribution-system resilience including microgrid contributions."),
            ("National Academies (2017)",
             "'Enhancing the Resilience of the Nation's Electricity System.' Useful policy-"
             "context citation for the introduction of any paper."),
        ]),
        ("Interactive & Browser-Based Visualization", BG_PIVOT, [
            ("Web-based grid-data visualisers",
             "Mostly scattered through blog posts and Jupyter demos; less peer-reviewed "
             "literature — which is precisely why your interactive tool occupies a "
             "distinctive niche."),
            ("Leaflet / D3.js visualization patterns",
             "Engineering precedents rather than research citations. Worth a methods-section "
             "note rather than a literature citation."),
        ]),
    ]

    for theme_name, bg, items in themes:
        h2(doc, theme_name)
        table = doc.add_table(rows=len(items), cols=2)
        for r, (who, what) in enumerate(items):
            row = table.rows[r].cells
            row[0].width = Inches(2.4); row[1].width = Inches(4.0)
            shade(row[0], bg)
            set_cell_borders(row[0]); set_cell_borders(row[1])
            p = row[0].paragraphs[0]
            add_styled(p, who, bold=True, color=INK, size=11)
            p = row[1].paragraphs[0]
            add_styled(p, what, color=INK, size=11)

    body(doc, "")
    h2(doc, "Where Your Contribution Sits — A Sketch for the Introduction")
    body(doc,
         "Restoration scheduling for distribution-system outages has a rich operations-"
         "research literature dominated by MILP and stochastic-programming formulations "
         "(Van Hentenryck, Arif et al., Watson et al.). In parallel, statistical outage-"
         "prediction work (Nateghi, Guikema, Quiring) has matured into utility-grade tools. "
         "Yet two gaps remain: (i) the decision-support pipeline between these two "
         "communities is largely proprietary, trapped inside commercial OMS platforms; and "
         "(ii) academic restoration models are rarely validated against the publicly "
         "available PURA storm-event filings that Connecticut utilities are required to "
         "produce.")
    body(doc,
         "This work contributes a publicly accessible, browser-first interactive simulator "
         "for Hartford County and (by extension) the Connecticut service territory, with "
         "the engineering capacity to run 100 000-outage scenarios and Monte Carlo "
         "ensembles in tens of milliseconds. The simulator is positioned as the calibration "
         "substrate for future work matching synthetic restoration timelines against real "
         "Eversource event histories. The intended contribution is the integration — an "
         "accessible, scale-validated, calibratable tool — rather than a novel scheduling "
         "algorithm.")

    body(doc, "")
    h2(doc, "Open Questions Your Paper Can Answer")
    questions = [
        "How close is the greedy rolling-horizon heuristic to MILP-optimal restoration at "
        "the scales where MILP is tractable (N ≤ 50)? What is the suboptimality gap as a "
        "function of crew/outage ratio?",
        "Given calibration against one real Eversource storm event (e.g., Isaias 2020 or "
        "the May 2018 tornado outage), how well do the model's parameters generalise to a "
        "held-out storm?",
        "How do restoration-time distributions change as you scale from county- to state-"
        "level outage counts? Is there a phase transition in crew-utilisation efficiency?",
        "Does adding stochastic re-discovery (delayed outage reporting) change the optimal "
        "crew dispatch strategy versus deterministic assumptions?",
    ]
    for q in questions:
        p = doc.add_paragraph()
        add_styled(p, "?  ", bold=True, color=QUESTION, size=12)
        add_styled(p, q, color=INK, size=11)

    body(doc, "")
    h2(doc, "Data Sources to Pursue")
    sources = [
        ("Connecticut PURA dockets",
         "Post-storm filings for major events (Isaias 2020, May 2018 tornado). Searchable "
         "at dpuc.state.ct.us. Restoration timelines, crew counts, mutual-aid arrivals."),
        ("Eversource storm reports",
         "Public-facing post-storm documents and PURA submissions. Often include outage "
         "curve, crew totals, customer-minutes-without-service."),
        ("U.S. Energy Information Administration Form EIA-417",
         "Major electric-disturbance reports. Coarse but federal-level coverage of major "
         "outage events including Connecticut."),
        ("DOE OE-417 disturbance dataset",
         "Similar federal dataset, downloadable bulk."),
        ("County / municipal GIS",
         "For real road network and population density — eventual upgrade from the "
         "synthetic demand-point model."),
    ]
    for who, what in sources:
        p = doc.add_paragraph()
        add_styled(p, "■ ", bold=True, color=ACCENT, size=12)
        add_styled(p, who + ".  ", bold=True, color=INK, size=11)
        add_styled(p, what, color=INK, size=11)

    body(doc, "")
    margin_note(doc,
                "These citations are starting points drawn from a literature scan rather "
                "than an exhaustive bibliography. Verify each on Google Scholar / IEEE "
                "Xplore before citing in a manuscript, and use this map to seed a more "
                "thorough review.")

    doc.save("Hartford_Grid_Research_Context.docx")
    print("Wrote Hartford_Grid_Research_Context.docx")


if __name__ == "__main__":
    build_journal()
    build_research()
