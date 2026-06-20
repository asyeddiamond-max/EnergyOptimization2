"""Builds the two deliverable .docx files:

  Hartford_Grid_Dev_Journal.docx     — colorful tabular development log
  Hartford_Grid_Research_Context.docx — research papers + niche analysis

Upload either to Google Drive (drag into drive.google.com) and Drive will
auto-convert to a native Google Doc.
"""
from docx import Document
from docx.shared import Pt, RGBColor, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


# Colour palette — same semantics as JOURNAL.html.
INK       = RGBColor(0x3B, 0x2F, 0x24)
ACCENT    = RGBColor(0x8B, 0x3A, 0x2E)
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


def shade(cell, hex_color):
    """Add a background fill to a table cell (python-docx has no direct API)."""
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
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    add_styled(p, text, bold=True, color=ACCENT, size=22, font="Iowan Old Style")


def h2(doc, text):
    p = doc.add_paragraph()
    add_styled(p, text, bold=True, color=ACCENT, size=15, font="Georgia")


def margin_note(doc, text):
    p = doc.add_paragraph()
    add_styled(p, text, italic=True, color=RGBColor(0x70, 0x56, 0x38), size=10)


def body(doc, text):
    p = doc.add_paragraph()
    add_styled(p, text, color=INK, size=11)


def tag_color(kind):
    return {
        "Build": (BUILD, BG_BUILD),
        "Fix": (FIX, BG_FIX),
        "Question": (QUESTION, BG_QUESTION),
        "Decision": (DECISION, BG_DECISION),
        "Pivot": (PIVOT, BG_PIVOT),
        "Perf": (PERF, BG_PERF),
    }.get(kind, (INK, "FFFFFF"))


def add_entry_table(doc, rows):
    """rows = list of (when, kind, detail) tuples."""
    table = doc.add_table(rows=1 + len(rows), cols=3)
    table.autofit = False
    widths = [Inches(0.9), Inches(0.9), Inches(4.6)]
    # Header
    hdr = table.rows[0].cells
    for i, (c, w, txt) in enumerate(zip(hdr, widths, ("WHEN", "KIND", "ENTRY"))):
        c.width = w
        shade(c, BG_HEADER)
        set_cell_borders(c)
        p = c.paragraphs[0]
        add_styled(p, txt, bold=True, color=RGBColor(0x5B, 0x45, 0x28), size=10)
    # Rows
    for r, (when, kind, detail) in enumerate(rows, start=1):
        row = table.rows[r].cells
        for c, w in zip(row, widths):
            c.width = w
            set_cell_borders(c)
        # When
        p = row[0].paragraphs[0]
        add_styled(p, when, italic=True, color=RGBColor(0x70, 0x56, 0x38), size=10)
        # Kind
        col, bg = tag_color(kind)
        shade(row[1], bg)
        p = row[1].paragraphs[0]
        add_styled(p, kind, bold=True, color=col, size=10)
        # Detail (supports list of (text, **opts) tuples for emphasis)
        p = row[2].paragraphs[0]
        if isinstance(detail, str):
            add_styled(p, detail, color=INK, size=11)
        else:
            for piece in detail:
                if isinstance(piece, str):
                    add_styled(p, piece, color=INK, size=11)
                else:
                    text, opts = piece
                    add_styled(p, text, color=INK, size=11, **opts)


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
               italic=True, color=RGBColor(0x6B, 0x56, 0x3B), size=12)
    add_styled(p, "    A. Syed Diamond  ·  Spring–Summer 2026",
               italic=True, color=RGBColor(0x6B, 0x56, 0x3B), size=10)

    # Legend
    body(doc, " ")
    legend = doc.add_paragraph()
    for label, color in [
        ("Build", BUILD), ("Fix", FIX), ("Perf", PERF),
        ("Question", QUESTION), ("Decision", DECISION), ("Pivot", PIVOT),
    ]:
        add_styled(legend, " ■ ", color=color, size=11, bold=True)
        add_styled(legend, label + "   ", color=INK, size=10)

    # Chapter I
    h2(doc, "Chapter I — Foundations")
    margin_note(doc, "Establishing the simulation, the synthetic grid, and the first interactive controls.")
    add_entry_table(doc, [
        ("Initial", "Build",
         "Synthetic Hartford County grid: 29 town boundaries, population-weighted demand points, "
         "k-means substation placement, randomised feeders + laterals, mulberry32 PRNG for "
         "reproducibility. Browser-first interactive on Leaflet."),
        ("Initial", "Build",
         "Greedy rolling-horizon scheduler with realistic mode: 12 h assessment delay, 14 h "
         "workdays, log-normal repair durations, mutual-aid waves at 0/24/48 h, 25 mph travel × "
         "1.5 road-multiplier, log-normal repair times capped at 12 h."),
    ])

    # Chapter II
    h2(doc, "Chapter II — The Five Alternatives")
    margin_note(doc, "Five orthogonal directions to make the simulation faster & more capable.")
    add_entry_table(doc, [
        ("Alt #1", "Build",
         "Closed-form equation for instant restoration-time estimate. Powers the live readout."),
        ("Alt #2", "Build",
         "Pre-computed scenario library — 12 named scenarios in scenarios/, loadable from a dropdown."),
        ("Alt #3", "Build",
         "WebAssembly scheduler in Rust (#![no_std], custom inline Taylor-series math, bump "
         "allocator, parallel-array heap, spatial grid hash). Artifact at wasm/scheduler.wasm."),
        ("Alt #3", "Fix",
         "Honest benchmark: WASM consistently 2–3× slower than V8 JS. Custom math is no match for "
         "V8's intrinsics. Conclusion: JS scheduler already wins. WASM kept as reference build."),
        ("Alt #4", "Question",
         "\"move onto #4\""),
        ("Alt #4", "Build",
         "FastAPI backend (07_server.py) with /api/schedule and /api/monte_carlo. CORS open. "
         "Dockerfile for deployment."),
    ])

    # Chapter III
    h2(doc, "Chapter III — The Scaling Saga")
    margin_note(doc, "Where a 25 000-outage × 5 000-crew max-settings stress test ran for eight minutes — and then half a second.")
    add_entry_table(doc, [
        ("Server v0", "Question",
         "\"its taking forever to load … 25k outages × 5 000 crews\""),
        ("Step 1", "Perf",
         "+5× — NumPy vectorisation. np.argmin over masked distance array; np.searchsorted on "
         "sorted discovery list for fast-forward lookup."),
        ("Step 2", "Decision",
         "User: \"do B\". KD-tree (#1) was tried and proved slower in realistic mode because "
         "discovered-fraction is low early on. Capped K to 256 — useful only at non-realistic "
         "dense regimes."),
        ("Step 3", "Perf",
         "+14× — Numba JIT of the entire dispatch loop with inline binary heap, inline haversine, "
         "inline Mulberry32. 2 k × 100 outages → 24 ms. Process pool tried for Monte Carlo but "
         "Windows spawn overhead beat it."),
        ("Step 4", "Pivot",
         "User: \"make the model survive even unrealistic scenarios … going to scale to "
         "Connecticut.\" Skipped MILP / calibration; focused on raw scalability."),
        ("Step 5", "Perf",
         "+246× — Spatial grid hash (G = sqrt(N/5) cells, Chebyshev ring expansion) plus an "
         "incrementally-maintained n_available counter. The counter is the real hero: when no "
         "work is discovered yet, crews fast-forward to the next discovery via binary search "
         "instead of doing a full grid scan."),
    ])

    # Benchmark table
    body(doc, " ")
    h2(doc, "Benchmark snapshot")
    bench = doc.add_table(rows=6, cols=3)
    for row in bench.rows:
        for cell in row.cells:
            set_cell_borders(cell)
    bench_rows = [
        ("Scenario", "Before", "After"),
        ("2 k × 100", "~minutes", "< 10 ms"),
        ("25 k × 500", "~minutes", "70 ms"),
        ("25 k × 5 000 (worst case)", "118 s", "480 ms"),
        ("50 k × 1 000", "untested / hours", "220 ms"),
        ("100 k × 2 000 (CT projection)", "infeasible", "660 ms"),
    ]
    for r, (a, b, c) in enumerate(bench_rows):
        cells = bench.rows[r].cells
        cells[0].text = ""; cells[1].text = ""; cells[2].text = ""
        is_header = r == 0
        for c_cell, txt in zip(cells, (a, b, c)):
            if is_header:
                shade(c_cell, BG_HEADER)
            p = c_cell.paragraphs[0]
            add_styled(p, txt, bold=is_header, color=INK, size=11)

    # Chapter IV
    h2(doc, "Chapter IV — Deployment & Polishing")
    margin_note(doc, "From localhost to a public Render URL, with a four-failure deploy saga along the way.")
    add_entry_table(doc, [
        ("Deploy", "Build",
         "Render Blueprint (render.yaml) auto-provisions the backend on push. Dockerfile pins "
         "fastapi / uvicorn / numpy / scipy / numba."),
        ("Deploy", "Fix",
         "Failure #1: matplotlib + numpy required. Cause: 05_generate_artifacts.py imports "
         "matplotlib unconditionally. Added matplotlib to image."),
        ("Deploy", "Fix",
         "Failure #2: FileNotFoundError: data/hartford_boundary.json. Wrapped import in "
         "try/except Exception. Still failed."),
        ("Deploy", "Fix",
         "Failure #3: same error. Reason: 05_generate_artifacts.py raises SystemExit, which "
         "inherits from BaseException, not Exception — Python deliberately makes except Exception "
         "skip it. Stopped importing 05_generate_artifacts entirely."),
        ("Frontend", "Build",
         "Auto-warm + auto-detect: no-cors GET on page load wakes the Render container; /version "
         "probe at 5 s / 30 s / 60 s. Health dot goes gray → amber → green. Plan restoration "
         "falls back to in-browser when server offline."),
        ("Frontend", "Build",
         "Server progress bar — exponential asymptote toward 90 % while waiting on the atomic "
         "server call. Tuned so Render cold starts (~30–60 s) still feel like motion."),
        ("Frontend", "Question",
         "\"why did you stop with those images that we used to have for when the plan restoration "
         "works\""),
        ("Frontend", "Build",
         "Flat per-job dispatch log inside Numba scheduler; server returns full jobs[] per crew. "
         "Browser renderPlan() extracted so both local and server paths produce the same colored "
         "crew depots + numbered repair circles + canvas point cloud."),
    ])

    # Chapter V
    h2(doc, "Chapter V — Conversations & Direction")
    margin_note(doc, "The questions that steered the work.")
    add_entry_table(doc, [
        ("Mid-saga", "Question",
         "\"MLP/calibration is what I want to do if it helps leads me towards more publishable "
         "research contributions\""),
        ("Mid-saga", "Pivot",
         "Pitched MILP optimal scheduler (1 day; needs no external data) vs. Eversource "
         "calibration (1 day code; bottlenecked on data access via PURA dockets). Recommended "
         "MILP first."),
        ("Mid-saga", "Question",
         "\"the real storm data is a lot later. We need to make this more scalable and more "
         "precise for Hartford county first … going to need to handle even heavier scenarios when "
         "scaled up to connecticut\""),
        ("Mid-saga", "Pivot",
         "Skipped MILP. Refocused on raw scalability so the model can survive CT-wide projection. "
         "Result: the Chapter III speedups."),
        ("Now", "Decision",
         "Next milestones queued, not yet built: MILP optimal scheduler for small N (greedy "
         "optimality gap); Eversource / PURA storm calibration once data acquired; WebGPU as "
         "engineering polish — deferred since Numba already handles CT scale."),
    ])

    # Coda
    h2(doc, "Coda")
    margin_note(doc, "Where the project stands at the moment of writing.")
    body(doc,
         "The interactive simulation is live at GitHub Pages; the server backend at "
         "hartford-grid-server.onrender.com auto-warms on page load and serves Numba-compiled "
         "scheduler calls in tens of milliseconds. The map paints colored crew depots, numbered "
         "repair circles, and a canvas point cloud — the visualisation parity the project "
         "started with, now at Connecticut scale. The road ahead is MILP comparison and "
         "PURA-grounded calibration; the engineering is done.")

    doc.save("Hartford_Grid_Dev_Journal.docx")
    print("Wrote Hartford_Grid_Dev_Journal.docx")


# =================== Build the Research Context ===================

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
               italic=True, color=RGBColor(0x6B, 0x56, 0x3B), size=12)
    add_styled(p, "    Companion to the development journal",
               italic=True, color=RGBColor(0x6B, 0x56, 0x3B), size=10)

    body(doc, "")
    h2(doc, "What This Project Is, In One Paragraph")
    body(doc,
         "A browser-first, county-specific interactive simulation of post-storm distribution-grid "
         "restoration. Models 100k+ outages and 5 000+ crews at Connecticut scale in under a "
         "second per scenario, with a server backend exposing Monte Carlo ensembles. The "
         "greedy rolling-horizon scheduler accounts for damage-assessment delay, log-normal "
         "repair durations, mutual-aid waves, workday clamps, and crew-routing heuristics. "
         "Designed as a foundation for calibration against real Eversource / PURA storm "
         "post-mortem data and for benchmarking against an MILP optimal scheduler.")

    body(doc, "")
    h2(doc, "The Niche You Are Exploring")
    margin_note(doc, "Reading of the academic + industry landscape; revise as you find more sources.")

    niche_points = [
        ("Most academic work on grid restoration is offline batch optimisation.",
         "Coffrin, Van Hentenryck, and collaborators have produced strong MILP and convex-"
         "relaxation models for transmission restoration. Less work targets distribution-level, "
         "county-scale, and almost none of it is interactive."),
        ("Most utility decision-support tools are proprietary and inaccessible.",
         "Eversource, Avangrid, and others use commercial outage-management systems (OMS) like "
         "OSI Monarch or GE PowerOn. These run in control rooms and are not accessible for "
         "academic exploration."),
        ("The synthetic-grid corpus targets transmission, not distribution.",
         "ARPA-E's GRID DATA program and Texas A&M's synthetic networks deliver transmission-"
         "scale test cases. County-resolution distribution grids with realistic storm-outage "
         "patterns are scarce."),
        ("Browser-first, real-time interactive grid simulation at this fidelity is rare.",
         "There are a few public demos but most are toy-scale (≤ 100 nodes). Running 100 000 "
         "outages + 5 000 crews + Monte Carlo in a browser-backed-by-API pipeline is a "
         "differentiator."),
        ("Calibration against real PURA / Eversource storm filings is largely untouched in published academic work.",
         "Statistical outage-prediction papers exist (Nateghi, Quiring, Guikema). Restoration-"
         "timeline calibration is much less common — partly because the data lives in regulatory "
         "filings rather than open datasets."),
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
               "a publicly accessible, scale-validated, calibratable interactive grid-resilience "
               "simulator for a specific real-world utility service territory. The contribution "
               "is the integration — the engineering of an accessible tool with research-grade "
               "behaviour — rather than a new algorithm.",
               color=INK, size=11)

    body(doc, "")
    h2(doc, "Literature Map by Theme")
    margin_note(doc, "Authors and groups whose work directly intersects this project. Verify each citation independently — these are starting points for your own search.")

    themes = [
        ("Grid Restoration Optimisation (MILP / Stochastic)",
         "BG_BUILD",
         [
            ("Van Hentenryck, P.; Coffrin, C. et al.",
             "Last-mile restoration formulations and convex relaxations of power flow for "
             "restoration. Key starting point for MILP comparison."),
            ("Arif, A.; Wang, Z.; Wang, J.; Mather, B.; Bashualdo, H.; Zhao, D.",
             "Multi-stage distribution-system restoration with stochastic repair times. Closely "
             "matches your problem statement."),
            ("Watson, J-P.; Greenberg, H.; Hart, W. (Sandia)",
             "Power-infrastructure restoration scheduling under uncertainty. Foundational."),
            ("Castillo, A. (2014)",
             "Survey of restoration models. Useful for situating your greedy among the broader "
             "model family."),
         ]),
        ("Storm-Induced Outage Modelling & Prediction",
         "BG_PERF",
         [
            ("Nateghi, R.; Guikema, S.; Quiring, S.",
             "Statistical models for hurricane-induced power-outage durations and counts. "
             "Directly relevant once you have real Eversource data."),
            ("Han, S-R.; Guikema, S.; Quiring, S. et al.",
             "Outage-prediction model evaluation against historical events. Useful template for "
             "validation methodology."),
            ("Liu, H.; Davidson, R.; Apanasovich, T.",
             "Spatial generalised linear mixed models for storm outage prediction."),
         ]),
        ("Synthetic Grid Generation",
         "BG_DECISION",
         [
            ("Birchfield, A. B.; Xu, T.; Gegner, K. M.; Shetye, K. S.; Overbye, T. J. (Texas A&M)",
             "Synthetic transmission grid construction methodology. Transmission-level, but the "
             "methods (k-means substation placement, demand allocation) directly informed your "
             "distribution-level approach."),
            ("Schweitzer Engineering / IEEE PES Distribution Test Feeders",
             "Standard feeder datasets (IEEE 13, 34, 123-node). Useful as ground-truth shape "
             "tests for the synthetic-feeder logic."),
         ]),
        ("Crew Routing & Vehicle Routing Variants",
         "BG_FIX",
         [
            ("Toth, P.; Vigo, D. (eds.)",
             "The Vehicle Routing Problem textbook. Foundational for understanding where your "
             "greedy sits in the broader VRP / job-shop landscape."),
            ("Perrier, N.; Langevin, A.; Campbell, J. F.",
             "Survey of operations-research models for snow plowing — analogous routing/"
             "scheduling problem with crews dispatched after disruption."),
            ("Solomon, M.",
             "VRPTW benchmark instances. Standard test set for time-window variants."),
         ]),
        ("Resilience Metrics & Frameworks",
         "BG_QUESTION",
         [
            ("Panteli, M.; Mancarella, P.",
             "Power-system resilience under extreme weather. Defines metrics like 'resilience "
             "trapezoid' which could frame your output."),
            ("Bie, Z.; Lin, Y.; Li, G.; Li, F.",
             "Survey of distribution-system resilience including microgrid contributions."),
            ("National Academies (2017)",
             "'Enhancing the Resilience of the Nation's Electricity System.' Useful policy-context "
             "citation for the introduction of any paper."),
         ]),
        ("Interactive & Browser-Based Visualization",
         "BG_PIVOT",
         [
            ("Halberstam, Y.; Ginsberg, J. (or similar grid-data visualisation work)",
             "Web-based grid-data visualisers are scattered through blog posts and Jupyter "
             "demos; less peer-reviewed literature here — which is precisely why your "
             "interactive tool occupies a distinctive niche."),
            ("Leaflet / D3.js visualization patterns",
             "Engineering precedents rather than research citations. Worth a methods-section "
             "note rather than a literature citation."),
         ]),
    ]

    for theme_name, bg, items in themes:
        h2(doc, theme_name)
        bg_color = {"BG_BUILD":BG_BUILD,"BG_FIX":BG_FIX,"BG_QUESTION":BG_QUESTION,
                    "BG_DECISION":BG_DECISION,"BG_PIVOT":BG_PIVOT,"BG_PERF":BG_PERF}[bg]
        table = doc.add_table(rows=len(items), cols=2)
        for r, (who, what) in enumerate(items):
            row = table.rows[r].cells
            row[0].width = Inches(2.4); row[1].width = Inches(4.0)
            shade(row[0], bg_color)
            set_cell_borders(row[0]); set_cell_borders(row[1])
            p = row[0].paragraphs[0]
            add_styled(p, who, bold=True, color=INK, size=11)
            p = row[1].paragraphs[0]
            add_styled(p, what, color=INK, size=11)

    body(doc, "")
    h2(doc, "Where Your Contribution Sits — A Sketch for the Introduction")
    body(doc,
         "Restoration scheduling for distribution-system outages has a rich operations-research "
         "literature dominated by MILP and stochastic-programming formulations (Van Hentenryck, "
         "Arif et al., Watson et al.). In parallel, statistical outage-prediction work (Nateghi, "
         "Guikema, Quiring) has matured into utility-grade tools. Yet two gaps remain: (i) the "
         "decision-support pipeline between these two communities is largely proprietary, "
         "trapped inside commercial OMS platforms; and (ii) academic restoration models are "
         "rarely validated against the publicly available PURA storm-event filings that "
         "Connecticut utilities are required to produce.")
    body(doc,
         "This work contributes a publicly accessible, browser-first interactive simulator for "
         "Hartford County and (by extension) the Connecticut service territory, with the "
         "engineering capacity to run 100 000-outage scenarios and Monte Carlo ensembles in "
         "tens of milliseconds. The simulator is positioned as the calibration substrate for "
         "future work matching synthetic restoration timelines against real Eversource event "
         "histories. The intended contribution is the integration — an accessible, scale-"
         "validated, calibratable tool — rather than a novel scheduling algorithm.")

    body(doc, "")
    h2(doc, "Open Questions Your Paper Can Answer")
    questions = [
        "How close is the greedy rolling-horizon heuristic to MILP-optimal restoration at the "
        "scales where MILP is tractable (N ≤ 50)? What is the suboptimality gap as a function "
        "of crew/outage ratio?",
        "Given calibration against one real Eversource storm event (e.g., Isaias 2020 or the "
        "May 2018 tornado outage), how well do the model's parameters generalise to a held-out "
        "storm?",
        "How do restoration-time distributions change as you scale from county- to state-level "
        "outage counts? Is there a phase transition in crew-utilisation efficiency?",
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
         "Post-storm filings for major events (Isaias 2020, May 2018 tornado). Searchable at "
         "dpuc.state.ct.us. Restoration timelines, crew counts, mutual-aid arrivals."),
        ("Eversource storm reports",
         "Public-facing post-storm documents and PURA submissions. Often include outage curve, "
         "crew totals, customer-minutes-without-service."),
        ("U.S. Energy Information Administration Form EIA-417",
         "Major electric-disturbance reports. Coarse but federal-level coverage of major outage "
         "events including Connecticut."),
        ("DOE OE-417 disturbance dataset",
         "Similar federal dataset, downloadable bulk."),
        ("County / municipal GIS",
         "For real road network and population density — eventual upgrade from the synthetic "
         "demand-point model."),
    ]
    for who, what in sources:
        p = doc.add_paragraph()
        add_styled(p, "■ ", bold=True, color=ACCENT, size=12)
        add_styled(p, who + ".  ", bold=True, color=INK, size=11)
        add_styled(p, what, color=INK, size=11)

    body(doc, "")
    margin_note(doc,
                "These citations are starting points drawn from a literature scan rather than "
                "an exhaustive bibliography. Verify each on Google Scholar / IEEE Xplore before "
                "citing in a manuscript, and use this map to seed a more thorough review.")

    doc.save("Hartford_Grid_Research_Context.docx")
    print("Wrote Hartford_Grid_Research_Context.docx")


if __name__ == "__main__":
    build_journal()
    build_research()
