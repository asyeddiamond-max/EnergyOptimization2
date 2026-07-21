"""
make_research_brief.py -- render the 2-page research brief PDF for Prof. Wanik
from the placement-validation finding (24_/25_/26_). Content is fixed prose;
figures are the committed PNGs. Regenerate after editing text or figures:
    python make_research_brief.py
"""
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Image,
                                Table, TableStyle, KeepTogether, HRFlowable)

HERE = Path(__file__).parent
OUT = HERE / "research_brief_public_data_outages.pdf"
USABLE_W = letter[0] - 1.5 * inch  # 0.75in margins both sides

INK = colors.HexColor("#111827")
RED = colors.HexColor("#b91c1c")
BLUE = colors.HexColor("#1d4ed8")
GREY = colors.HexColor("#6b7280")
LIGHT = colors.HexColor("#f3f4f6")

styles = getSampleStyleSheet()
H_TITLE = ParagraphStyle("t", parent=styles["Title"], fontSize=16, leading=19,
                         textColor=INK, spaceAfter=2, alignment=TA_CENTER)
SUB = ParagraphStyle("sub", parent=styles["Normal"], fontSize=9.5, leading=12,
                     textColor=GREY, alignment=TA_CENTER, spaceAfter=3)
H2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=11.5, leading=13,
                    textColor=INK, spaceBefore=9, spaceAfter=3)
BODY = ParagraphStyle("body", parent=styles["Normal"], fontSize=9.7, leading=13.2,
                      textColor=INK, alignment=TA_JUSTIFY, spaceAfter=4)
CALL = ParagraphStyle("call", parent=BODY, fontSize=10, leading=13.5,
                      textColor=INK, leftIndent=8, rightIndent=8, spaceBefore=2,
                      spaceAfter=2, backColor=LIGHT, borderPadding=6)
CAP = ParagraphStyle("cap", parent=styles["Normal"], fontSize=8, leading=10,
                     textColor=GREY, alignment=TA_CENTER, spaceBefore=2, spaceAfter=8)
FOOT = ParagraphStyle("foot", parent=styles["Normal"], fontSize=7.6, leading=9.5,
                      textColor=GREY)
Q = ParagraphStyle("q", parent=BODY, fontSize=9.7, leading=12.8, leftIndent=14,
                   spaceAfter=3, bulletIndent=2)


def img(path, aspect):
    w = USABLE_W
    return Image(str(HERE / path), width=w, height=w / aspect)


def main():
    doc = SimpleDocTemplate(str(OUT), pagesize=letter,
                            topMargin=0.7 * inch, bottomMargin=0.6 * inch,
                            leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                            title="Reconstructing storm outage footprints from public data",
                            author="Abid")
    S = []
    S.append(Paragraph("How Far Can Public Data Reconstruct Storm-Outage Footprints?", H_TITLE))
    S.append(Paragraph("A Connecticut validation of storm-report-based outage placement against ORNL EAGLE-I", SUB))
    S.append(Paragraph("Research brief &nbsp;&middot;&nbsp; Abid &nbsp;&middot;&nbsp; July 2026 &nbsp;&middot;&nbsp; "
                       "built on the CT storm-restoration simulator (with Alex Luo)", SUB))
    S.append(HRFlowable(width="100%", thickness=0.6, color=GREY, spaceBefore=2, spaceAfter=6))

    S.append(Paragraph("The question", H2))
    S.append(Paragraph(
        "Public datasets are increasingly used to model where storms knock out electric power: NOAA/NCEI "
        "records geolocated wind and tornado damage, and ORNL&rsquo;s EAGLE-I archive publishes county-level "
        "customers-without-power every 15 minutes. A natural question follows &mdash; <b>how far can public data "
        "alone reconstruct the spatial footprint of an outage event, and where does it break?</b> Using "
        "Connecticut as a testbed, I placed a storm&rsquo;s outages by proximity to real NCEI damage reports and "
        "then checked, against an independent county-resolution record, whether the outages landed in the counties "
        "that actually lost power.", BODY))

    S.append(Paragraph("Data and method", H2))
    S.append(Paragraph(
        "<b>Placement (the thing being tested):</b> outages are drawn toward real NCEI Storm Events point reports "
        "(Thunderstorm-Wind / Tornado latitude&ndash;longitude with wind magnitude), weighted by local customer "
        "exposure from U.S. Census tracts. <b>Ground truth (independent):</b> ORNL EAGLE-I county-level "
        "customers-out &mdash; the utilities&rsquo; own outage-map archive, which the placement never sees. "
        "<b>Test:</b> every Connecticut storm from 2018&ndash;2024 that has both a set of NCEI point reports and a "
        "real EAGLE-I county signal (11 convective storms), scored by the Pearson correlation between the "
        "placement&rsquo;s per-county outage share and EAGLE-I&rsquo;s, across the state&rsquo;s 8 counties; plus "
        "Connecticut&rsquo;s other major outage events for context.", BODY))

    S.append(Paragraph("Finding 1 &mdash; for convective storms, public reports locate outages well", H2))
    S.append(Paragraph(
        "Across the 11 convective storms, report-weighted placement reproduces the real county footprint far "
        "better than a population-only baseline: <b>median Pearson r rises from 0.51 to 0.80</b>, the "
        "report-weighted method wins in <b>8 of 11</b> storms, and reaches r &ge; 0.5 in <b>10 of 11</b>. This "
        "includes the May 2018 macroburst/tornado outbreak (135,000 customers, the third-largest event here), "
        "placed at r = 0.96. In plain terms: when a storm produces geolocated convective-damage reports, those "
        "public points are enough to say <i>which counties</i> lost power.", BODY))
    S.append(KeepTogether([img("output/placement_fidelity_summary.png", 2.77),
                           Paragraph("Fig. 1 &mdash; Two convective storms vs. EAGLE-I. Left: May 2018 hit the "
                                     "populated southwest, densely reported; report-weighted placement (red) "
                                     "tracks the real footprint (black). Right: the Oct 2020 derecho tracked "
                                     "rural NE Connecticut, which the population-biased report network "
                                     "under-samples &mdash; the lone failure.", CAP)]))

    S.append(Paragraph("Finding 2 &mdash; but public reports are blind to Connecticut&rsquo;s biggest storms", H2))
    S.append(Paragraph(
        "NCEI only geolocates <i>convective</i> damage. Tropical storms and synoptic high-wind events are logged "
        "as county-<i>zone</i> records with no coordinates; winter storms produce no wind reports at all. So for "
        "the events that cause Connecticut&rsquo;s largest outages, the method has essentially no data to work "
        "with:", BODY))

    tbl_data = [
        ["Event", "Peak customers out", "Usable NCEI points"],
        ["Isaias (Aug 2020) — tropical", "725,700", "1"],
        ["March 2018 nor’easters — winter", "170,041", "0"],
        ["Halloween 2019 windstorm — synoptic", "90,583", "0"],
        ["Oct 2019 windstorm — synoptic", "45,516", "0"],
        ["Ida remnants (Sep 2021) — tropical", "36,822", "0"],
        ["Henri (Aug 2021) — tropical", "32,279", "0"],
    ]
    t = Table(tbl_data, colWidths=[USABLE_W * 0.5, USABLE_W * 0.28, USABLE_W * 0.22],
              repeatRows=1)
    t.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#fee2e2")),
        ("ROWBACKGROUNDS", (0, 2), (-1, -1), [colors.white, LIGHT]),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, INK),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (0, -1), 7),
    ]))
    S.append(t)
    S.append(Paragraph(
        "Of Connecticut&rsquo;s six largest outage events in this window, three &mdash; Isaias, the March 2018 "
        "nor&rsquo;easters, and the 2019 Halloween windstorm &mdash; carry near-zero usable point reports. The "
        "method is blind to exactly the storms that matter most.", BODY))
    S.append(KeepTogether([img("output/storm_applicability_census.png", 2.50),
                           Paragraph("Fig. 2 &mdash; Left: per-storm county-footprint accuracy, report-weighted "
                                     "(red) vs. population-only (blue); dashed line r = 0.5. Right: the "
                                     "applicability gap &mdash; the largest events (blue) sit at zero point "
                                     "reports, far from the convective cluster (red).", CAP)]))

    S.append(Paragraph("What this means, and where I&rsquo;d value your guidance", H2))
    S.append(Paragraph(
        "Public-report placement is a real but <b>narrow</b> tool: it reconstructs the county-level footprint of "
        "convective storms, yet is structurally blind to the tropical, synoptic, and winter events that dominate "
        "Connecticut&rsquo;s outage totals, and it fails unpredictably when convection tracks rural areas the "
        "report network under-samples. This is, on real data, a concrete version of the limit EAGLE-I&rsquo;s "
        "authors noted qualitatively &mdash; that reconstructing outage detail from public data alone is not "
        "generally possible. The clear way past it is data at finer-than-county resolution. A few questions where "
        "your perspective would be especially valuable:", BODY))
    for q in [
        "Is feeder- or town-level outage / restoration data (Eversource or UI) accessible for research &mdash; "
        "even for a handful of benchmark storms such as Isaias or the 2018 nor&rsquo;easters?",
        "Would validating outage placement at <i>sub-county</i> resolution, and extending it beyond convective "
        "storms, be a contribution worth pursuing jointly?",
        "Which framing would you steer this toward &mdash; the &ldquo;limits of public data&rdquo; angle, or a "
        "modeling-improvement angle &mdash; and are there venues you&rsquo;d have in mind?",
        "EAGLE-I is national; would adding a second utility or state materially strengthen the result?",
    ]:
        S.append(Paragraph(q, Q, bulletText="•"))

    S.append(Spacer(1, 4))
    S.append(HRFlowable(width="100%", thickness=0.5, color=GREY, spaceBefore=2, spaceAfter=4))
    S.append(Paragraph(
        "<b>Data &amp; reproducibility.</b> NOAA/NCEI Storm Events Database; ORNL EAGLE-I recorded outages "
        "2014&ndash;2025 (doi:10.6084/m9.figshare.24237376); U.S. Census TIGER/2020 tracts. Placement and scoring "
        "code (Python, Monte-Carlo over 3,000 outages &times; 30 seeds per storm) available on request. Prepared "
        "as a discussion brief; figures and per-storm tables reproduce from the committed scripts.", FOOT))

    doc.build(S)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
