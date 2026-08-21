from __future__ import annotations

import csv
import html
import io
import json
import os
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


def _csv_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _csv_bytes(headers: list[str], rows: Iterable[Iterable[Any]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\r\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow([_csv_cell(value) for value in row])
    return ("\ufeff" + stream.getvalue()).encode("utf-8")


def build_csv_zip(summary: dict[str, Any]) -> bytes:
    game = summary["game"]
    files: dict[str, bytes] = {}
    files["manifest.csv"] = _csv_bytes(
        ["項目", "値"],
        [
            ["schema_version", summary.get("schema_version")],
            ["generated_at", datetime.utcnow().isoformat()],
            ["game_id", game.get("id")],
            ["game_name", game.get("name")],
            ["started_at", game.get("started_at") or game.get("created_at")],
            ["completed_at", game.get("completed_at")],
            ["viewer_scope", summary.get("viewer_scope")],
        ],
    )

    overall_headers = [
        "クラブID", "クラブ", "最終期売上", "売上順位", "最終純資産", "純資産順位",
        "優勝回数", "準優勝回数", "平均順位", "シーズン数", "ホーム平均入場者数",
        "入場者順位", "最終ファンベース", "ファンベース順位", "最終フォロワー数",
        "フォロワー順位", "最終スポンサー数", "スポンサー順位", "次年度スポンサー数",
    ]
    files["overall_results.csv"] = _csv_bytes(
        overall_headers,
        (
            [
                row.get("club_id"), row.get("club_name"), row.get("final_sales_amount"),
                row.get("final_sales_rank"), row.get("final_equity_amount"), row.get("final_equity_rank"),
                row.get("championship_count"), row.get("runner_up_count"), row.get("average_rank"),
                row.get("seasons_played"), row.get("average_home_attendance"), row.get("attendance_rank"),
                row.get("final_fanbase"), row.get("fanbase_rank"), row.get("final_followers"),
                row.get("followers_rank"), row.get("final_sponsor_count"), row.get("sponsor_rank"),
                row.get("next_sponsor_count"),
            ]
            for row in summary.get("overall_results", [])
        ),
    )

    standing_fields = ["season_id", "season_number", "year_label", "club_id", "club_name", "rank", "played", "won", "drawn", "lost", "gf", "ga", "gd", "points"]
    files["season_standings.csv"] = _csv_bytes(
        ["シーズンID", "シーズン", "年度", "クラブID", "クラブ", "順位", "試合", "勝", "分", "敗", "得点", "失点", "得失点", "勝点"],
        ([row.get(field) for field in standing_fields] for row in summary.get("season_standings", [])),
    )

    metric_fields = [
        "season_id", "season_number", "year_label", "rank", "points", "revenue", "expense", "net",
        "closing_balance", "average_home_attendance", "fanbase", "followers", "sponsor_count",
        "next_sponsor_count", "team_power", "bankrupt", "points_penalty",
    ]
    metric_rows = []
    for review in summary.get("club_reviews", []):
        for row in review.get("season_metrics", []):
            metric_rows.append([review.get("club_id"), review.get("club_name"), *[row.get(field) for field in metric_fields]])
    files["season_metrics.csv"] = _csv_bytes(
        ["クラブID", "クラブ", "シーズンID", "シーズン", "年度", "順位", "勝点", "売上", "費用", "純収支", "期末残高", "ホーム平均入場者数", "ファンベース", "フォロワー", "スポンサー数", "次年度スポンサー数", "チーム力", "債務超過", "勝点ペナルティ"],
        metric_rows,
    )

    decision_rows = []
    for review in summary.get("club_reviews", []):
        for row in review.get("decisions", []):
            decision_rows.append(
                [
                    review.get("club_id"), review.get("club_name"), row.get("season_number"),
                    row.get("year_label"), row.get("month_index"), row.get("month_name"),
                    row.get("decision_state"), row.get("inputs"), row.get("committed_by"),
                    row.get("committed_at"), row.get("income"), row.get("expense"),
                    row.get("closing_balance"), row.get("rank"), row.get("points"), row.get("matches"),
                ]
            )
    files["decisions.csv"] = _csv_bytes(
        ["クラブID", "クラブ", "シーズン", "年度", "月番号", "月", "確定状態", "意思決定", "確定者", "確定日時", "収入", "費用", "残高", "順位", "勝点", "試合結果"],
        decision_rows,
    )

    files["highlights.csv"] = _csv_bytes(
        ["クラブID", "クラブ", "カテゴリ", "内容"],
        (
            [row.get("club_id"), row.get("club_name"), row.get("category"), row.get("message")]
            for row in summary.get("highlights", [])
        ),
    )

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


def _register_fonts() -> tuple[str, str]:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfbase.ttfonts import TTFont

    bundled_font = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "NotoSansJP-Variable.ttf"
    candidates = [
        (
            os.getenv("RESULT_PDF_FONT_REGULAR"),
            os.getenv("RESULT_PDF_FONT_BOLD"),
        ),
        (str(bundled_font), str(bundled_font)),
        (
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        ),
        (
            "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
            "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
        ),
    ]
    for regular, bold in candidates:
        if regular and os.path.exists(regular):
            try:
                regular_options = {"subfontIndex": 0} if regular.lower().endswith((".ttc", ".otc")) else {}
                bold_path = bold or regular
                bold_options = {"subfontIndex": 0} if bold_path.lower().endswith((".ttc", ".otc")) else {}
                pdfmetrics.registerFont(TTFont("ResultJP", regular, **regular_options))
                pdfmetrics.registerFont(TTFont("ResultJP-Bold", bold_path, **bold_options))
                return "ResultJP", "ResultJP-Bold"
            except Exception:
                continue
    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
    return "HeiseiKakuGo-W5", "HeiseiKakuGo-W5"


def _fmt(value: Any) -> str:
    if value is None:
        return "記録なし"
    if isinstance(value, bool):
        return "あり" if value else "なし"
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.2f}"
    if isinstance(value, (int, float)):
        return f"{int(value):,}"
    return str(value)


def _paragraph(text: Any, style: Any) -> Any:
    from reportlab.platypus import Paragraph

    return Paragraph(html.escape(_fmt(text)).replace("\n", "<br/>"), style)


def _line_chart(metrics: list[dict[str, Any]], key: str, title: str, color: Any, font_name: str) -> Any:
    from reportlab.graphics.charts.linecharts import HorizontalLineChart
    from reportlab.graphics.shapes import Drawing, String

    recorded = [row for row in metrics if row.get(key) is not None]
    drawing = Drawing(360, 155)
    drawing.add(String(10, 137, title, fontName=font_name, fontSize=10))
    if not recorded:
        drawing.add(String(40, 75, "記録なし", fontName=font_name, fontSize=9))
        return drawing
    chart = HorizontalLineChart()
    chart.x = 40
    chart.y = 25
    chart.height = 95
    chart.width = 300
    chart.data = [[float(row[key]) for row in recorded]]
    chart.categoryAxis.categoryNames = [f"S{row['season_number']}" for row in recorded]
    chart.categoryAxis.labels.fontName = font_name
    chart.categoryAxis.labels.fontSize = 7
    chart.valueAxis.labels.fontName = font_name
    chart.valueAxis.labels.fontSize = 7
    chart.lines[0].strokeColor = color
    chart.lines[0].strokeWidth = 2
    chart.joinedLines = 1
    drawing.add(chart)
    return drawing


def build_pdf(summary: dict[str, Any]) -> bytes:
    from pypdf import PdfReader
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        BaseDocTemplate,
        Frame,
        KeepTogether,
        NextPageTemplate,
        PageBreak,
        PageTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    regular_font, bold_font = _register_fonts()
    styles = getSampleStyleSheet()
    title = ParagraphStyle("JPTitle", parent=styles["Title"], fontName=bold_font, fontSize=24, leading=31, textColor=colors.HexColor("#16324F"), alignment=TA_CENTER)
    heading = ParagraphStyle("JPHeading", parent=styles["Heading2"], fontName=bold_font, fontSize=15, leading=20, textColor=colors.HexColor("#16324F"), spaceBefore=8, spaceAfter=8)
    subheading = ParagraphStyle("JPSubheading", parent=styles["Heading3"], fontName=bold_font, fontSize=11, leading=15, textColor=colors.HexColor("#28536B"), spaceBefore=6, spaceAfter=5)
    body = ParagraphStyle("JPBody", parent=styles["BodyText"], fontName=regular_font, fontSize=8.5, leading=12)
    small = ParagraphStyle("JPSmall", parent=body, fontSize=6.8, leading=9)
    cell = ParagraphStyle("JPCell", parent=body, fontSize=6.5, leading=8)

    output = io.BytesIO()

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        width, _ = canvas._pagesize
        canvas.setFont(regular_font, 7)
        canvas.setFillColor(colors.HexColor("#5F6C7B"))
        canvas.drawString(14 * mm, 8 * mm, summary["game"]["name"])
        canvas.drawRightString(width - 14 * mm, 8 * mm, f"{doc.page}")
        canvas.restoreState()

    portrait_frame = Frame(14 * mm, 14 * mm, A4[0] - 28 * mm, A4[1] - 30 * mm, id="portrait-frame")
    land = landscape(A4)
    landscape_frame = Frame(12 * mm, 14 * mm, land[0] - 24 * mm, land[1] - 30 * mm, id="landscape-frame")
    doc = BaseDocTemplate(
        output,
        pagesize=A4,
        title=f"{summary['game']['name']} 結果サマリー",
        author="Club Management Game",
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )
    doc.addPageTemplates([
        PageTemplate(id="portrait", pagesize=A4, frames=[portrait_frame], onPage=footer),
        PageTemplate(id="landscape", pagesize=land, frames=[landscape_frame], onPage=footer),
    ])

    story: list[Any] = [
        Spacer(1, 35 * mm),
        _paragraph("ゲーム結果サマリー", title),
        Spacer(1, 10 * mm),
        _paragraph(summary["game"]["name"], ParagraphStyle("GameName", parent=heading, alignment=TA_CENTER, fontSize=18)),
        Spacer(1, 8 * mm),
        _paragraph(f"プレイシーズン数: {summary['game']['seasons_played']}", body),
        _paragraph(f"ゲーム開始: {summary['game'].get('started_at') or summary['game']['created_at']}", body),
        _paragraph(f"ゲーム終了: {summary['game']['completed_at']}", body),
        _paragraph("本レポートは複数の評価軸を提示し、単一の総合優勝者は決定しません。", body),
        NextPageTemplate("landscape"),
        PageBreak(),
        _paragraph("総合結果", heading),
    ]

    overall_header = ["クラブ", "売上\n(順位)", "純資産\n(順位)", "優勝/準優勝", "平均順位", "平均入場者\n(順位)", "ファン\n(順位)", "フォロワー\n(順位)", "スポンサー\n(順位)", "次年度スポンサー"]
    overall_rows = [[_paragraph(label, cell) for label in overall_header]]
    for row in summary.get("overall_results", []):
        overall_rows.append([
            _paragraph(row.get("club_name"), cell),
            _paragraph(f"{_fmt(row.get('final_sales_amount'))} ({_fmt(row.get('final_sales_rank'))})", cell),
            _paragraph(f"{_fmt(row.get('final_equity_amount'))} ({_fmt(row.get('final_equity_rank'))})", cell),
            _paragraph(f"{_fmt(row.get('championship_count'))}/{_fmt(row.get('runner_up_count'))}", cell),
            _paragraph(row.get("average_rank"), cell),
            _paragraph(f"{_fmt(row.get('average_home_attendance'))} ({_fmt(row.get('attendance_rank'))})", cell),
            _paragraph(f"{_fmt(row.get('final_fanbase'))} ({_fmt(row.get('fanbase_rank'))})", cell),
            _paragraph(f"{_fmt(row.get('final_followers'))} ({_fmt(row.get('followers_rank'))})", cell),
            _paragraph(f"{_fmt(row.get('final_sponsor_count'))} ({_fmt(row.get('sponsor_rank'))})", cell),
            _paragraph(row.get("next_sponsor_count"), cell),
        ])
    overall_table = Table(overall_rows, repeatRows=1, colWidths=[26*mm, 25*mm, 25*mm, 18*mm, 16*mm, 26*mm, 24*mm, 24*mm, 24*mm, 24*mm])
    overall_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#28536B")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), bold_font),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#AAB7C4")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F7FA")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.extend([overall_table, Spacer(1, 8 * mm), _paragraph("シーズン別最終順位", heading)])

    standing_rows = [[_paragraph(label, cell) for label in ["Season", "年度", "順位", "クラブ", "試合", "勝", "分", "敗", "得点", "失点", "得失点", "勝点"]]]
    for row in summary.get("season_standings", []):
        standing_rows.append([_paragraph(row.get(key), cell) for key in ("season_number", "year_label", "rank", "club_name", "played", "won", "drawn", "lost", "gf", "ga", "gd", "points")])
    standings_table = Table(standing_rows, repeatRows=1, colWidths=[16*mm, 19*mm, 14*mm, 36*mm, 14*mm, 12*mm, 12*mm, 12*mm, 14*mm, 14*mm, 16*mm, 14*mm])
    standings_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#28536B")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#AAB7C4")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F7FA")]),
    ]))
    story.append(standings_table)

    for review in summary.get("club_reviews", []):
        story.extend([PageBreak(), _paragraph(f"クラブレビュー: {review['club_name']}", heading)])
        metrics = review.get("season_metrics", [])
        if metrics:
            story.append(KeepTogether([
                _line_chart(metrics, "rank", "順位推移（数値が小さいほど上位）", colors.HexColor("#D1495B"), regular_font),
                _line_chart(metrics, "closing_balance", "期末残高推移", colors.HexColor("#2A9D8F"), regular_font),
            ]))
        metric_rows = [[_paragraph(label, cell) for label in ["Season", "順位", "売上", "費用", "純収支", "残高", "入場者", "ファン", "フォロワー", "スポンサー", "チーム力", "債務超過"]]]
        for row in metrics:
            metric_rows.append([_paragraph(row.get(key), cell) for key in ("season_number", "rank", "revenue", "expense", "net", "closing_balance", "average_home_attendance", "fanbase", "followers", "sponsor_count", "team_power", "bankrupt")])
        metric_table = Table(metric_rows, repeatRows=1, colWidths=[15*mm, 13*mm, 24*mm, 24*mm, 24*mm, 24*mm, 19*mm, 19*mm, 19*mm, 18*mm, 18*mm, 16*mm])
        metric_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#28536B")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#AAB7C4")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.extend([metric_table, Spacer(1, 5 * mm), _paragraph("ハイライト", subheading)])
        for highlight in review.get("highlights", []):
            story.append(_paragraph(f"・{highlight['message']}", body))

        story.extend([Spacer(1, 5 * mm), _paragraph("意思決定タイムライン", subheading)])
        decision_rows = [[_paragraph(label, cell) for label in ["Season", "月", "意思決定", "確定者", "試合結果", "収入", "費用", "残高", "順位", "勝点"]]]
        for row in review.get("decisions", []):
            inputs = ", ".join(f"{key}={_fmt(value)}" for key, value in row.get("inputs", {}).items()) or "記録なし"
            matches = ", ".join(
                f"{'H' if match.get('home') else 'A'} vs {match.get('opponent') or '記録なし'} "
                f"{_fmt(match.get('score_for'))}-{_fmt(match.get('score_against'))}"
                for match in row.get("matches", [])
            ) or "記録なし"
            decision_rows.append([
                _paragraph(row.get("season_number"), cell), _paragraph(row.get("month_name"), cell),
                _paragraph(inputs, small), _paragraph(row.get("committed_by"), cell),
                _paragraph(matches, small),
                _paragraph(row.get("income"), cell), _paragraph(row.get("expense"), cell),
                _paragraph(row.get("closing_balance"), cell), _paragraph(row.get("rank"), cell),
                _paragraph(row.get("points"), cell),
            ])
        decision_table = Table(decision_rows, repeatRows=1, colWidths=[13*mm, 13*mm, 62*mm, 25*mm, 35*mm, 22*mm, 22*mm, 24*mm, 11*mm, 11*mm])
        decision_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#28536B")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#AAB7C4")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F7FA")]),
        ]))
        story.append(decision_table)

    doc.build(story)
    pdf_bytes = output.getvalue()
    reader = PdfReader(io.BytesIO(pdf_bytes))
    if not reader.pages:
        raise ValueError("Generated result PDF has no pages")
    return pdf_bytes


def safe_export_filename(value: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "_", value).strip(" ._")
    return cleaned or "club-management-game"
