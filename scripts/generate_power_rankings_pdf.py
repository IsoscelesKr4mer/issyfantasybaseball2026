#!/usr/bin/env python3
"""
Generate a shareable Power Rankings PDF for the Issaquah Swingers Fantasy Baseball League.

Usage:
    python3 scripts/generate_power_rankings_pdf.py <week_number>

Reads data/power-rankings.json and produces power-rankings/power-rankings-week-NN.pdf
"""

import json
import os
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether
)
from reportlab.pdfgen import canvas


# -- Color palette (dark theme inspired) --
BG_DARK = colors.HexColor("#1a1a2e")
BG_CARD = colors.HexColor("#16213e")
BG_HEADER = colors.HexColor("#0f3460")
ACCENT_GOLD = colors.HexColor("#e2b714")
ACCENT_GREEN = colors.HexColor("#4ecca3")
ACCENT_RED = colors.HexColor("#e74c3c")
TEXT_WHITE = colors.HexColor("#f5f5f5")
TEXT_GRAY = colors.HexColor("#b0b0b0")
TEXT_DARK = colors.HexColor("#1a1a2e")

TIER_COLORS = {
    "elite": colors.HexColor("#e2b714"),
    "contender": colors.HexColor("#4ecca3"),
    "mid": colors.HexColor("#7b8794"),
    "cellar": colors.HexColor("#e74c3c"),
}

TIER_BG = {
    "elite": colors.HexColor("#3d3510"),
    "contender": colors.HexColor("#1a3a30"),
    "mid": colors.HexColor("#2a2d30"),
    "cellar": colors.HexColor("#3d1515"),
}


def load_data(repo_root):
    pr_path = repo_root / "data" / "power-rankings.json"
    with open(pr_path, "r") as f:
        return json.load(f)


def get_week_rankings(data, week):
    """Get rankings for a specific week. If week == last_updated_week, use top-level rankings."""
    if week == data["last_updated_week"]:
        return data["rankings"]
    for snap in data.get("weekly_snapshots", []):
        if snap["week"] == week:
            return snap["rankings"]
    return None


def fmt_record(ap):
    parts = [f"{ap['w']}-{ap['l']}"]
    if ap.get("t", 0) > 0:
        parts[0] += f"-{ap['t']}"
    return parts[0]


def fmt_cats(cats):
    return f"{cats['w']}-{cats['l']}-{cats['t']}"


def delta_str(delta):
    if delta > 0:
        return f"+{delta}"
    elif delta < 0:
        return str(delta)
    return "-"


def delta_color(delta):
    if delta > 0:
        return ACCENT_GREEN
    elif delta < 0:
        return ACCENT_RED
    return TEXT_GRAY


def build_pdf(data, week, output_path):
    rankings = get_week_rankings(data, week)
    if not rankings:
        print(f"ERROR: No rankings found for week {week}")
        sys.exit(1)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "PRTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=22,
        textColor=TEXT_DARK,
        alignment=TA_CENTER,
        spaceAfter=4,
    )

    subtitle_style = ParagraphStyle(
        "PRSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=11,
        textColor=colors.HexColor("#666666"),
        alignment=TA_CENTER,
        spaceAfter=12,
    )

    tier_header_style = ParagraphStyle(
        "TierHeader",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=13,
        textColor=TEXT_DARK,
        spaceBefore=14,
        spaceAfter=6,
    )

    team_name_style = ParagraphStyle(
        "TeamName",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        textColor=TEXT_DARK,
        leading=14,
    )

    analysis_style = ParagraphStyle(
        "Analysis",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        textColor=colors.HexColor("#444444"),
        leading=11,
        spaceBefore=2,
    )

    stat_style = ParagraphStyle(
        "Stat",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        textColor=TEXT_DARK,
        alignment=TA_CENTER,
    )

    methodology_style = ParagraphStyle(
        "Methodology",
        parent=styles["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=7.5,
        textColor=colors.HexColor("#888888"),
        alignment=TA_CENTER,
        spaceBefore=6,
        spaceAfter=16,
    )

    story = []

    # Title
    story.append(Paragraph("ISSAQUAH SWINGERS", title_style))
    story.append(Paragraph(f"Power Rankings - Week {week}", subtitle_style))
    story.append(Paragraph(data.get("methodology", ""), methodology_style))

    # Separator
    story.append(HRFlowable(
        width="100%", thickness=1.5,
        color=colors.HexColor("#e2b714"),
        spaceBefore=2, spaceAfter=12
    ))

    # Season summary strip
    total_teams = len(rankings)
    # Each week has 10 categories x 5 matchups = 50 category decisions
    # Total category decisions = weeks * 50, but we show aggregate W-L-T across all teams
    total_cat_w = sum(r["cumulative_cats"]["w"] for r in rankings)
    total_cat_l = sum(r["cumulative_cats"]["l"] for r in rankings)
    total_cat_t = sum(r["cumulative_cats"]["t"] for r in rankings)
    avg_ap_w = sum(r["cumulative_ap"]["w"] for r in rankings) / total_teams

    strip_data = [[
        Paragraph(f'<b>{total_teams}</b> Teams Ranked', stat_style),
        Paragraph(f'<b>{week}</b> Weeks Played', stat_style),
        Paragraph(f'<b>{avg_ap_w:.1f}</b> Avg AP Wins', stat_style),
    ]]
    strip_table = Table(strip_data, colWidths=[2.3 * inch, 2.3 * inch, 2.3 * inch])
    strip_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0f0f0")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(strip_table)
    story.append(Spacer(1, 14))

    # Group by tier
    tiers_order = ["elite", "contender", "mid", "cellar"]
    tier_labels = {
        "elite": "ELITE",
        "contender": "CONTENDERS",
        "mid": "MIDDLE OF THE PACK",
        "cellar": "CELLAR DWELLERS",
    }

    for tier in tiers_order:
        tier_teams = [r for r in rankings if r.get("tier") == tier]
        if not tier_teams:
            continue

        tier_color = TIER_COLORS.get(tier, TEXT_GRAY)
        tier_bg = TIER_BG.get(tier, colors.HexColor("#f5f5f5"))

        # Tier header bar
        tier_header_data = [[
            Paragraph(
                f'<font color="{tier_color.hexval()}">{tier_labels[tier]}</font>',
                ParagraphStyle(
                    "TierLabel",
                    fontName="Helvetica-Bold",
                    fontSize=10,
                    textColor=tier_color,
                    alignment=TA_LEFT,
                )
            )
        ]]
        tier_header_table = Table(tier_header_data, colWidths=[6.9 * inch])
        tier_header_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8f8f8")),
            ("LINEBELOW", (0, 0), (-1, -1), 2, tier_color),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(tier_header_table)
        story.append(Spacer(1, 4))

        for team in tier_teams:
            rank = team["rank"]
            name = team["name"]
            delta = team.get("delta", 0)
            ap = team["cumulative_ap"]
            cats = team["cumulative_cats"]
            analysis = team.get("analysis", "")
            history = team.get("history", [])
            week_ap = {}
            week_cats = {}

            # Get this week's performance from history or week_ap/week_cats
            if history:
                latest = [h for h in history if h["week"] == week]
                if latest:
                    week_ap = latest[0].get("ap", {})
                    week_cats = latest[0].get("cats", {})
            if not week_ap and "week_ap" in team:
                week_ap = team["week_ap"]
            if not week_cats and "week_cats" in team:
                week_cats = team["week_cats"]

            # Delta arrow
            d_str = delta_str(delta)
            d_color = delta_color(delta)

            # Build rank + delta cell
            rank_text = f'<font size="16"><b>#{rank}</b></font>'
            if delta != 0:
                arrow = "&#9650;" if delta > 0 else "&#9660;"
                rank_text += f'<br/><font size="8" color="{d_color.hexval()}">{arrow} {abs(delta)}</font>'
            else:
                rank_text += f'<br/><font size="8" color="#999999">--</font>'

            rank_para = Paragraph(rank_text, ParagraphStyle(
                "RankCell", alignment=TA_CENTER, leading=14,
            ))

            # Team name + tier badge
            name_para = Paragraph(
                f'<b>{name}</b>',
                ParagraphStyle("NameCell", fontName="Helvetica-Bold", fontSize=11, leading=14)
            )

            # Stats block
            ap_str = fmt_record(ap)
            cats_str = fmt_cats(cats)
            week_ap_str = fmt_record(week_ap) if week_ap else "N/A"
            week_cats_str = fmt_cats(week_cats) if week_cats else "N/A"

            stats_text = (
                f'<font size="8" color="#888888">CUMULATIVE AP:</font> <b>{ap_str}</b>'
                f'&nbsp;&nbsp;&nbsp;'
                f'<font size="8" color="#888888">CATS:</font> <b>{cats_str}</b>'
                f'<br/>'
                f'<font size="8" color="#888888">WEEK {week} AP:</font> {week_ap_str}'
                f'&nbsp;&nbsp;&nbsp;'
                f'<font size="8" color="#888888">CATS:</font> {week_cats_str}'
            )
            stats_para = Paragraph(stats_text, ParagraphStyle(
                "StatsCell", fontName="Helvetica", fontSize=9, leading=12,
            ))

            # Trend line from history
            trend_text = ""
            if history:
                ranks = sorted(history, key=lambda h: h["week"])
                rank_strs = []
                for h in ranks:
                    r = h.get("rank", 0)
                    if r == 0:
                        r = rank  # current week
                    rank_strs.append(f"Wk{h['week']}: #{r}")
                trend_text = " -> ".join(rank_strs)

            # Analysis
            analysis_para = Paragraph(
                analysis.replace("&rsquo;", "'").replace("&oacute;", "o"),
                analysis_style
            )

            # Build the team row as a mini table
            # Row 1: Rank | Name + Stats
            # Row 2: (span) Analysis + Trend

            inner_top = [[rank_para, [name_para, Spacer(1, 2), stats_para]]]
            inner_top_table = Table(inner_top, colWidths=[0.6 * inch, 6.3 * inch])
            inner_top_table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (0, 0), 4),
                ("RIGHTPADDING", (-1, -1), (-1, -1), 4),
            ]))

            # Trend line
            if trend_text:
                trend_para = Paragraph(
                    f'<font size="7" color="#999999">TREND: {trend_text}</font>',
                    ParagraphStyle("Trend", fontSize=7, leading=9)
                )
            else:
                trend_para = Spacer(1, 1)

            # Wrap everything in a card
            card_content = [[inner_top_table], [analysis_para]]
            if trend_text:
                card_content.append([trend_para])

            card_table = Table(card_content, colWidths=[6.9 * inch])

            card_styles = [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fafafa")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
                ("TOPPADDING", (0, 0), (-1, 0), 2),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                # Tier accent on left
                ("LINEBELOW", (0, 0), (0, 0), 0, tier_color),
            ]

            # Left border accent for tier
            card_styles.append(
                ("LINEBEFORE", (0, 0), (0, -1), 3, tier_color)
            )

            card_table.setStyle(TableStyle(card_styles))

            story.append(KeepTogether([card_table, Spacer(1, 6)]))

    # Footer
    story.append(Spacer(1, 16))
    story.append(HRFlowable(
        width="100%", thickness=0.5,
        color=colors.HexColor("#cccccc"),
        spaceBefore=4, spaceAfter=8
    ))
    footer_style = ParagraphStyle(
        "Footer",
        fontName="Helvetica-Oblique",
        fontSize=7,
        textColor=colors.HexColor("#aaaaaa"),
        alignment=TA_CENTER,
    )
    story.append(Paragraph("issaquahswingers.com | Issaquah Swingers Fantasy Baseball League | 2026 Season", footer_style))

    doc.build(story)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/generate_power_rankings_pdf.py <week_number>")
        sys.exit(1)

    week = int(sys.argv[1])
    repo_root = Path(__file__).resolve().parent.parent
    data = load_data(repo_root)

    output_dir = repo_root / "power-rankings"
    output_dir.mkdir(exist_ok=True)

    output_path = output_dir / f"power-rankings-week-{week:02d}.pdf"

    print(f"Generating power rankings PDF for Week {week}...")
    build_pdf(data, week, output_path)
    print(f"PDF saved to: {output_path}")
    print(f"File size: {output_path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
