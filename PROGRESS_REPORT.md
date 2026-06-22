# Hartford County Grid Simulation — Progress Report

**Author:** A. Syed Diamond
**Reporting period:** Initial server deployment (commit `d678d7d`) through commit `70606a9`
**Live interactive:** https://asyeddiamond-max.github.io/EnergyOptimization2/03_grid_simulation.html
**Live server backend:** https://hartford-grid-server.onrender.com

---

## TL;DR

In the reporting period, 25 commits transformed the simulator from a "FastAPI server is up but max settings (25 000 outages × 5 000 crews) takes minutes and crashes the page" prototype into a **Connecticut-scale, server-backed, browser-first research platform** that handles 100 000-outage scenarios in under a second, with seven realism factors, a calibration framework, customer-impact-weighted dispatch, crew specialization, multi-server batch sweeps, and complete deliverables (development journal + research context document).

The system is now ready to receive real Eversource / PURA storm data and produce a calibrated, validated restoration model — which is the next research milestone.

---

## 1 · Where We Started This Period

Reference point: the first commit that added the server backend (commit `d678d7d`, "Add Alternative #4: server-side compute backend").

At that point the simulator could:

- Generate a synthetic Hartford County distribution grid.
- Simulate storms with realistic outage patterns.
- Run a greedy rolling-horizon scheduler with seven realism factors.
- Visualize the result on a Leaflet map.
- Optionally route compute to a FastAPI server running pure-Python scheduler code.

It could **not** yet:

- Handle the user's stated stress test of 25 000 outages × 5 000 crews. The pure-Python server scheduler took minutes per call, made Monte Carlo ensembles infeasible.
- Recover from a Render free-tier cold start gracefully.
- Calibrate against real storm data.
- Distinguish line crews from tree crews.
- Prioritize outages by customer impact.
- Run scenarios across multiple servers.
- Show a customers-restored-over-time curve.

All of these capabilities were added during this reporting period.

---

## 2 · Performance Improvements

The single biggest engineering result is a **~100× to ~200× speedup** at the maximum-settings scenario, achieved through a sequence of algorithmic + JIT optimizations:

| Step | Optimization | 25k × 5000 time |
|------|-------------|----------------|
| Reference | Pure-Python scheduler on server (start of period) | ~minutes / unusable |
| Step 1 | NumPy vectorization (`scheduler_fast.py`) | ~30 s |
| Step 2 | KD-tree experiment (`scheduler_fast.py`) | regression in realistic mode (documented honestly) |
| Step 3 | Numba JIT of entire dispatch loop (`scheduler_numba.py`) | ~118 s |
| Step 4 | Spatial grid hash + Chebyshev ring expansion | improved smaller cases; 25k × 5000 still slow due to discovery thrashing |
| Step 5 | `n_available` counter — fast-forward when no work is discovered | **~0.48 s** (246× speedup vs Step 3) |
| Step 6 | Grid hash extended for customer-weighted scoring | 2.24 s with weighted mode enabled |
| Step 7 | Parallel tree/line subsystem dispatch under crew specialization | another ~1.5× when crew specialization toggle is on |
| Step 8 | Numba JIT pre-warm at server boot | eliminates the ~10 s first-call compile penalty |
| Step 9 | Gzip response compression | ~10× reduction in network response size at 25k outages |

**End-state benchmark at 25 000 outages × 5 000 crews, all toggles on (realistic + customer-priority + crew-specialization):** ~2–3 s end-to-end including network. Previously: not feasible.

**100 000-outage Connecticut-scale projection:** ~0.66 s in pure-nearest mode, well under a second.

---

## 3 · Capability Additions

### 3.1 Realism upgrades

- **Customer-impact-weighted dispatch (realism factor #4)** — instead of pure nearest-neighbor, the scheduler can prefer outages that restore more customers. `score(o) = customers(o) - weight × d²`. Empirically reduces total restoration time at 25k × 5000 from 72 h (pure-nearest) to 61.7 h, confirming this is not just cosmetic — it's a genuine plan-quality improvement.
- **Crew specialization (line vs tree crews)** — splits the crew fleet 80/20 (line/tree), tags 30% of outages as tree-blocked, runs two independent dispatch subsystems in parallel threads. Total restoration time = max(tree_subsystem, line_subsystem).

### 3.2 Research capabilities

- **Calibration framework (`/api/calibrate`)** — accepts an observed restoration curve from a real storm, runs SciPy Nelder-Mead optimization to find the parameter set (travel speed, assessment delay, workday hours, road multiplier) that best reproduces the curve. Self-test against synthetic data converges with 100× RMSE reduction in ~50 iterations. **Ready to receive real PURA / Eversource data.**
- **Optimal crew count search (`/api/recommend`)** — binary search over crew count to find the smallest fleet that achieves restoration within 15% of the theoretical floor. Server-side path drops this from ~5 minutes (in-browser JS) to ~10 seconds at 250 000 outages.
- **Monte Carlo ensembles (`/api/monte_carlo`)** — run N seeds in series (with optional process-pool parallelism at large scales). Returns mean / median / stddev / 5th / 95th percentiles.
- **Multi-server batch sweep (`/api/batch`)** — fan out N scenarios across worker URLs concurrently. Empty workers list = serial in-process. Designed for free-tier scaling: spin up additional Render free services and paste their URLs to scale linearly.

### 3.3 UX / quality-of-life

- **Auto-detect server health** — page-load probe + every-4-min keep-alive + visibility-change re-probe + auto-rewake on any failed probe.
- **"Wake server now" button** — manual override for forcing a wake when the dot has been red for a while.
- **`/version` endpoint** — frontend displays the commit SHA the running server was built from, so you can verify the deploy is current.
- **Asymptotic fake progress bar** during server calls — gives the user a sense of motion during the 30–60 s Render cold starts.
- **Customer-restored-over-time curve** — inline SVG line chart under the Total Restoration Time display. Visualizes what customer-priority actually changes.
- **Per-job dispatch visualization** restored after the server-backend regression — depots + numbered repair circles + canvas point cloud all draw correctly whether the plan came from local or server.

### 3.4 Deployment & infrastructure

- **Render Blueprint** (`render.yaml`) — auto-provisions the backend on free tier when the repo is connected.
- **Dockerfile** — pins exactly the dependencies needed (FastAPI, Uvicorn, Pydantic, NumPy, SciPy, Numba); intentionally excludes matplotlib to fit in Render's 512 MB free-tier RAM.
- **Auto-deploy on push** — every commit to `master` triggers a Render rebuild.

---

## 4 · Direction Changes During This Period

Three significant direction conversations shaped what got built:

### Conversation A — WebAssembly verdict

After honest benchmarking, the Rust-compiled WebAssembly scheduler (Alternative #3) was found to be **2-3× slower than V8 JS** at the scales we care about. Root cause: hand-rolled Taylor-series math (required because Windows toolchain blocked `libm`) is no match for V8's native intrinsics. **Decision: WASM kept as reference build, V8 JS remains the production browser scheduler.** This is one of the project's clearest "kill your darlings" moments and a defensible negative result worth documenting in any write-up.

### Conversation B — MILP vs calibration vs scalability

User initially identified MILP optimal scheduling + Eversource calibration as the research direction. After scoping, **user re-prioritized scalability first**: *"the real storm data is a lot later. We need to make this more scalable and more precise for Hartford county first. Want this model first to be able to survive against even these unrealistic scenarios for Hartford County as they are going to need to handle even heavier scenarios when scaled up to Connecticut."* This re-framing drove the entire grid-hash + n_available counter work that achieved Connecticut-scale capability.

### Conversation C — Adding missing realism factors before calibration

After scalability was solved, user wanted to add the two most-impactful missing realism factors (customer-impact weighting + crew specialization) **before** attempting calibration. This was the right move — calibration on a poorly specified model would just fit noise; better to calibrate after the model captures the right structure.

---

## 5 · What's Live Right Now

| Layer | URL / Location |
|------|---|
| Interactive simulator | https://asyeddiamond-max.github.io/EnergyOptimization2/03_grid_simulation.html |
| Server backend | https://hartford-grid-server.onrender.com |
| Health check | https://hartford-grid-server.onrender.com/health |
| Version (verify deploy) | https://hartford-grid-server.onrender.com/version |
| Source repository | https://github.com/asyeddiamond-max/EnergyOptimization2 |
| Development journal (HTML) | `JOURNAL.html` in repo |
| Development journal (Word) | `Hartford_Grid_Dev_Journal.docx` in repo |
| Research context document | `Hartford_Grid_Research_Context.docx` in repo |

---

## 6 · Honest Limitations

In the spirit of academic honesty, here is what the simulator **cannot** yet claim:

1. **It is not validated against real storm data.** The seven realism factors are each individually defensible against industry sources, and their aggregate output is order-of-magnitude correct against published Eversource event timelines, but no specific real event has been used to tune parameters. The calibration framework exists and is tested against synthetic data; real data ingestion is the next research step.
2. **Outage points are still 1:1 with repair locations**, not weighted by customer count in the topology sense (a substation outage doesn't restore thousands at once in the model; it still counts as one repair, just with a higher customer weight). This is a documented simplification that future work could address.
3. **The synthetic grid is plausibly shaped but is not the real Eversource topology.** Real distribution feeder data is proprietary. The synthetic generator produces feeder + lateral patterns with the right statistical character but is not a digital twin of any specific network.
4. **WebGPU (Alternative #5) was never implemented.** Deferred as engineering polish; Numba already handles Connecticut scale, so the urgency went away.

These limitations are documented in the journal so reviewers don't have to find them by reading code.

---

## 7 · Publishable Research Directions

The current state supports several plausible publication paths. Ranked by tractability:

### 7.1 Tool paper (easiest, most tractable)

A "software paper" describing the interactive simulator as a research instrument. Natural venues:

- **Journal of Open Source Software (JOSS)** — peer-reviewed but lightweight, optimized for research software. ~2 weeks to a few months turnaround.
- **SoftwareX (Elsevier)** — also a software-paper venue, slightly more traditional.
- **IEEE Access** — broader scope, faster than IEEE Transactions, accepts software-focused work.

This requires: a clean README, a permanent DOI (Zenodo gives one for free), demonstrations of scale, and documented architecture. Most of the prerequisites are already in the repo.

### 7.2 Algorithmic-improvement paper (well-scoped)

"Customer-impact-weighted greedy dispatch for distribution-system restoration: a real-utility heuristic that reduces total customer-minutes-without-service by X% at Hartford-County scale."

This is a clear, defensible engineering contribution. Compare pure-nearest vs customer-weighted on N synthetic scenarios, report restoration-time and customer-minutes deltas. Venue: **IEEE Transactions on Smart Grid** or **Electric Power Systems Research**.

### 7.3 Calibration / validation paper (needs PURA data first)

Once one or two real Eversource event timelines are in hand (Isaias 2020, May 2018 tornado, etc.), the calibration framework can produce a fit, and the calibrated model's predictions can be validated against a held-out storm. This is the **highest-impact** target but is **bottlenecked on data acquisition** from PURA dockets.

### 7.4 Joint paper with UConn Eversource Energy Center

The Wanik / Anagnostou / Cerrai group at UConn has the prediction side (where and how many outages); this work has the restoration side (how long until power is back). A joint paper presenting an end-to-end pipeline would be a strong contribution. Requires reaching out — possibly via your advisor.

### 7.5 Performance / engineering case study

Less common but viable for a teaching journal or a short note: "From minutes to milliseconds: algorithmic + JIT optimizations for distribution-grid restoration simulation at 100 000 outages." The 246× win story is genuinely interesting. Venue: **Computing in Science & Engineering** or similar.

**Recommended starting point:** combine 7.1 and 7.2. Write a tool paper for JOSS that includes the customer-impact-weighting result as a worked example. This is the lowest-friction path to a real publication and seeds everything else.

---

## 8 · Images / Data Needed for the Contribution

For the publications discussed above, you'll need a mix of images that already exist + ones you'd need to generate.

### Already available (in `output/` and screenshots)

- ✅ Hartford County boundary + 29 towns
- ✅ Synthetic distribution grid (substations, feeders, laterals)
- ✅ Storm overlay
- ✅ Restoration plan (depots + numbered crews + point cloud)
- ✅ Outage-curve PNG (existing matplotlib artifact)

### Need to generate (straightforward, can be done now)

- 📝 **Architecture diagram** — browser ↔ Render server ↔ Numba scheduler, showing the data flow.
- 📝 **Benchmark chart** — bar chart of times across scenarios (2k, 25k, 100k) and modes (pure-Python, NumPy, Numba, Numba+grid+nAvail).
- 📝 **Side-by-side restoration maps** — same scenario rendered with (a) pure-nearest dispatch, (b) customer-weighted dispatch. The visual difference is the publishable evidence.
- 📝 **Customer-restored curve comparison** — overlay the two curves from the side-by-side, showing customer-priority recovers customers faster.
- 📝 **Calibration synthetic test** — observed (synthetic) curve vs initial-guess simulation vs calibrated-fit simulation. Already runs from the self-test; just need to capture it as a figure.
- 📝 **Sensitivity plot** — restoration time vs crew count for several storm sizes. The batch sweep can generate this.
- 📝 **Monte Carlo distribution histogram** — for a fixed scenario, the spread across 100 seeds. Calibration's `evaluations` payload has this data.

### Need to acquire (research-data prerequisite)

- 🎯 **One real Eversource event timeline** — hourly customer-restored count from a PURA storm filing or Eversource post-mortem report. The Isaias 2020 docket (PURA 20-08-11) and the May 15 2018 tornado event are the two most documented options. Look at:
  - https://www.dpuc.state.ct.us (PURA dockets)
  - Eversource investor / regulatory filings (publicly available)
  - DOE OE-417 disturbance reports (federal-level)
  - The UConn Eversource Energy Center team may have shared anonymized data with academic collaborators

Once one such timeline is digitized into the `/api/calibrate` format (list of `(hour, customers_restored)`), the calibration phase can produce the figures that turn the project into a validated-realistic model.

---

## 9 · What I'd Recommend for the Next Quarter

If continuing the work:

1. **Pursue PURA / Eversource data access first.** This is the single highest-impact item and is gated on you, not on me/code. Email your advisor, ask about UConn collaboration, search PURA dockets, ping FOIA-style requests. Without this, items below produce a tool paper; with it, you produce a validated-research paper.
2. **Generate the side-by-side figures** above. Half a day of work; they're the strongest visual evidence the customer-impact-weighting result is meaningful.
3. **Write a JOSS draft** alongside the figure work. JOSS papers are short (~1500 words) and the prereqs are mostly done. Realistic 2–4 weeks of writing time.
4. **Reach out to the UConn group** with the JOSS draft as a credible artifact. Even if joint authorship isn't on the table, citing them and contextualizing this work as the restoration counterpart to their prediction work is the right framing.

---

## 10 · Appendix — Detailed Commit List Since Period Start

| Commit | Title | Theme |
|--------|-------|-------|
| `d678d7d` | Add Alternative #4: server-side compute backend | period-start reference |
| `26e65ad` | Add Render blueprint + complete Dockerfile deps for #4 backend | deployment |
| `6e2d768` | Add matplotlib to Docker image (05_generate_artifacts.py import dep) | deployment fix |
| `151568e` | Add progress indicator for server-side Plan restoration + Monte Carlo | UX |
| `3d074d2` | Scale scheduler to Connecticut-wide (100k+ outages) via spatial grid hash + n_available counter | **performance milestone — 246× speedup** |
| `c18d0e3` | Auto-warm + auto-detect server backend with /version endpoint | UX / deployment |
| `c73e511` | Drop matplotlib from Docker image; make 05_generate_artifacts import optional | deployment fix |
| `fd87b7a` | Stop importing 05_generate_artifacts entirely in the server | deployment fix (Python SystemExit gotcha) |
| `3767771` | Return per-job dispatch sequence from server so map markers render | regression fix |
| `879a4db` | Add development journal + research context deliverables | documentation |
| `179cb7f` | Expand journal substantially: 14 chapters with verbatim user quotes | documentation |
| `90ed423` | Expand Chapter I into 10 sub-sections covering the full foundation work | documentation |
| `30311be` | Add Problems Faced sections: Chapter I sub-section + cross-project Appendix A | documentation |
| `3077fed` | Expand research context: specific paper citations with summaries | documentation |
| `f2b33bd` | Add Key terms vocab list under each research-paper citation | documentation |
| `b6a0615` | Center research context on UConn / Wanik / Eversource Energy Center group | documentation |
| `f88355e` | Route 'Find optimal crew count' through the server (Numba) when available | performance |
| `5d11943` | Fix Apply-to-slider crash at max settings: route through server toggle | bug fix |
| `de1d6a3` | Add customer-impact-weighted dispatch (realism factor #4 of 'add missing factors') | **research feature** |
| `8d32dbd` | Add calibration framework: tune realism parameters against observed curves | **research feature** |
| `86ccaab` | Add crew specialization (line vs tree crews) as opt-in toggle | research feature |
| `aacf832` | Add customers-restored-over-time curve overlay below restoration result | UX |
| `45e20e0` | Add multi-server batch sweep: fan out N scenarios across worker URLs in parallel | research feature |
| `a245b87` | Speed up all-toggles-on case: grid hash supports customer-weighting + parallel subsystems | performance |
| `88efa08` | Keep-alive: aggressive ping + auto-rewake + manual wake button | UX / reliability |
| `70606a9` | Three more speedup wins for max-settings scenarios | performance |

---

*Generated alongside the development journal (`JOURNAL.html`, `Hartford_Grid_Dev_Journal.docx`) and research context document (`Hartford_Grid_Research_Context.docx`), all of which are in the same repository.*
