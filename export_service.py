"""
SoMeet Web - Document Export Service
Generates professional Microsoft Word (.docx) files with typography & theme styling.
"""
import io
import docx
from docx.shared import Inches, Pt, RGBColor
from datetime import datetime


def generate_meeting_docx(
    title: str,
    date_str: str = "",
    speaker: str = "",
    summary_markdown: str = "",
    transcript_text: str = ""
) -> bytes:
    """
    Creates a styled Microsoft Word document with:
    - Calibri typography
    - Excel Theme Cerulean Blue (#5B9BD5) branding
    - Formatted Headings, Bullet Lists, and Checkboxes
    """
    doc = docx.Document()

    # Standard 1-inch margins
    for section in doc.sections:
        section.top_margin = Inches(1)
        section.bottom_margin = Inches(1)
        section.left_margin = Inches(1)
        section.right_margin = Inches(1)

    # Document Header / Brand
    brand_p = doc.add_paragraph()
    brand_run = brand_p.add_run("SoMeet • Executive Intelligence")
    brand_run.font.name = "Calibri"
    brand_run.font.size = Pt(9.5)
    brand_run.font.bold = True
    brand_run.font.color.rgb = RGBColor(91, 155, 213) # Excel Accent 5 #5B9BD5
    brand_p.paragraph_format.space_after = Pt(2)

    # Document Title
    title_p = doc.add_paragraph()
    title_run = title_p.add_run(title)
    title_run.font.name = "Calibri"
    title_run.font.size = Pt(22)
    title_run.font.bold = True
    title_run.font.color.rgb = RGBColor(30, 41, 59) # Deep Slate #1E293B
    title_p.paragraph_format.space_after = Pt(4)

    # Subtitle / Metadata Bar
    if not date_str:
        date_str = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    meta_p = doc.add_paragraph()
    meta_text = f"Date: {date_str}"
    if speaker:
        meta_text += f"   |   User: {speaker}"
    meta_run = meta_p.add_run(meta_text)
    meta_run.font.name = "Calibri"
    meta_run.font.size = Pt(10)
    meta_run.font.color.rgb = RGBColor(100, 116, 139) # Muted Slate
    meta_p.paragraph_format.space_after = Pt(14)

    # Add Divider Line
    divider = doc.add_paragraph()
    d_run = divider.add_run("―" * 48)
    d_run.font.color.rgb = RGBColor(220, 234, 247)
    divider.paragraph_format.space_after = Pt(12)

    # Summary Section
    if summary_markdown:
        lines = summary_markdown.splitlines()
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
            if line_str.startswith("### "):
                heading_text = line_str.replace("### ", "").strip()
                h = doc.add_paragraph()
                hrun = h.add_run(heading_text)
                hrun.font.name = "Calibri"
                hrun.font.size = Pt(13.5)
                hrun.font.bold = True
                hrun.font.color.rgb = RGBColor(75, 121, 161) # Royal Cerulean
                h.paragraph_format.space_before = Pt(12)
                h.paragraph_format.space_after = Pt(3)
            elif line_str.startswith("- [ ] "):
                action_text = line_str.replace("- [ ] ", "").strip()
                p = doc.add_paragraph(style='List Bullet')
                prun = p.add_run("☐  " + action_text.replace("**", ""))
                prun.font.name = "Calibri"
                prun.font.size = Pt(11)
                p.paragraph_format.space_after = Pt(2)
            elif line_str.startswith("- "):
                bullet_text = line_str.replace("- ", "").strip()
                p = doc.add_paragraph(style='List Bullet')
                prun = p.add_run(bullet_text.replace("**", ""))
                prun.font.name = "Calibri"
                prun.font.size = Pt(11)
                p.paragraph_format.space_after = Pt(2)
            else:
                p = doc.add_paragraph()
                prun = p.add_run(line_str)
                prun.font.name = "Calibri"
                prun.font.size = Pt(11)
                p.paragraph_format.space_after = Pt(4)

    # Verbatim Transcript Section
    if transcript_text:
        doc.add_paragraph().paragraph_format.space_after = Pt(8)
        th = doc.add_paragraph()
        th_run = th.add_run("Verbatim Speech Transcript")
        th_run.font.name = "Calibri"
        th_run.font.size = Pt(13.5)
        th_run.font.bold = True
        th_run.font.color.rgb = RGBColor(75, 121, 161)
        th.paragraph_format.space_before = Pt(14)
        th.paragraph_format.space_after = Pt(4)

        tp = doc.add_paragraph()
        tp_run = tp.add_run(transcript_text)
        tp_run.font.name = "Calibri"
        tp_run.font.size = Pt(11)
        tp.paragraph_format.line_spacing = 1.15
        tp.paragraph_format.space_after = Pt(8)

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()
