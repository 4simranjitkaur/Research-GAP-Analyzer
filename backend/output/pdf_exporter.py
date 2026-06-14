from fpdf import FPDF
import re
from datetime import date


def clean_markdown(text: str) -> list:
    """Convert markdown text into a list of (type, content) tuples."""
    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            lines.append(("blank", ""))
            continue

        # Headings
        heading_match = re.match(r"^(#{1,6})\s+(.*)", stripped)
        if heading_match:
            level = len(heading_match.group(1))
            content = heading_match.group(2).strip()
            # Clean inline markdown from heading
            content = re.sub(r"\*\*(.*?)\*\*", r"\1", content)
            content = re.sub(r"\*(.*?)\*", r"\1", content)
            lines.append(("heading", content, level))
            continue

        # Bullet points
        bullet_match = re.match(r"^[-*•]\s+(.*)", stripped)
        if bullet_match:
            content = bullet_match.group(1).strip()
            content = re.sub(r"\*\*(.*?)\*\*", r"\1", content)
            content = re.sub(r"\*(.*?)\*", r"\1", content)
            lines.append(("bullet", content))
            continue

        # Normal paragraph
        clean = re.sub(r"\*\*(.*?)\*\*", r"\1", stripped)
        clean = re.sub(r"\*(.*?)\*", r"\1", clean)
        clean = re.sub(r"`(.*?)`", r"\1", clean)
        lines.append(("text", clean))

    return lines


def safe(text: str) -> str:
    """Encode text safely for FPDF latin-1."""
    return text.encode("latin-1", errors="replace").decode("latin-1")


def export_to_pdf(topic: str, report: str, sources: list) -> bytes:
    pdf = FPDF()
    pdf.set_margins(left=20, top=20, right=20)
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    eff_w = 170  # 210mm - 20mm*2 margins

    # ── Title ──────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(20, 20, 20)
    pdf.cell(eff_w, 12, "Research Report", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(2)

    # ── Topic ──────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(50, 50, 50)
    topic_safe = safe(f"Topic: {topic}")
    pdf.multi_cell(eff_w, 8, topic_safe, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    # ── Date ───────────────────────────────────────────────
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(eff_w, 6, f"Generated: {date.today().strftime('%B %d, %Y')}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # ── Divider ────────────────────────────────────────────
    def divider():
        pdf.set_draw_color(200, 200, 200)
        pdf.line(20, pdf.get_y(), 20 + eff_w, pdf.get_y())
        pdf.ln(6)

    divider()

    # ── Report Body ────────────────────────────────────────
    parsed = clean_markdown(report)

    for item in parsed:
        kind = item[0]

        if kind == "blank":
            pdf.ln(3)

        elif kind == "heading":
            content = item[1]
            level = item[2]
            pdf.ln(3)
            if level <= 2:
                pdf.set_font("Helvetica", "B", 13)
                pdf.set_text_color(20, 20, 20)
            else:
                pdf.set_font("Helvetica", "B", 11)
                pdf.set_text_color(40, 40, 40)
            pdf.multi_cell(eff_w, 7, safe(content), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
            pdf.set_font("Helvetica", "", 11)
            pdf.set_text_color(30, 30, 30)

        elif kind == "bullet":
            content = item[1]
            pdf.set_font("Helvetica", "", 11)
            pdf.set_text_color(30, 30, 30)
            # Use x offset for indent, write bullet manually
            x = pdf.get_x()
            y = pdf.get_y()
            pdf.set_xy(20, y)
            pdf.cell(6, 6, "-")
            pdf.set_xy(26, y)
            pdf.multi_cell(eff_w - 6, 6, safe(content), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)

        elif kind == "text":
            content = item[1]
            if content.strip():
                pdf.set_font("Helvetica", "", 11)
                pdf.set_text_color(30, 30, 30)
                pdf.multi_cell(eff_w, 6, safe(content), new_x="LMARGIN", new_y="NEXT")
                pdf.ln(1)

    # ── Sources ────────────────────────────────────────────
    if sources:
        pdf.ln(4)
        divider()
        pdf.set_font("Helvetica", "B", 13)
        pdf.set_text_color(20, 20, 20)
        pdf.cell(eff_w, 8, "Sources Used", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(0, 80, 160)
        for i, url in enumerate(sources, 1):
            if url and url.strip():
                pdf.multi_cell(eff_w, 5, safe(f"{i}. {url}"), new_x="LMARGIN", new_y="NEXT")
                pdf.ln(1)

    return bytes(bytearray(pdf.output()))