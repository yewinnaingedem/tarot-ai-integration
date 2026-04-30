"""
Convert README.md → TarotAI_Backend_Documentation.docx
Upload the .docx to Google Drive and Google Docs will render it perfectly.
"""
import re
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

doc = Document()

# ── Page margins ──────────────────────────────────────────────
for section in doc.sections:
    section.top_margin    = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin   = Inches(1.2)
    section.right_margin  = Inches(1.2)

# ── Style helpers ─────────────────────────────────────────────
def set_font(run, size=11, bold=False, italic=False, color=None, mono=False):
    run.bold   = bold
    run.italic = italic
    run.font.size = Pt(size)
    if mono:
        run.font.name = "Courier New"
    if color:
        run.font.color.rgb = RGBColor(*color)

def add_heading(text, level):
    sizes   = {1: 20, 2: 16, 3: 13}
    colors  = {1: (31, 73, 125), 2: (47, 84, 150), 3: (68, 114, 196)}
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14 if level == 1 else 8)
    p.paragraph_format.space_after  = Pt(4)
    run = p.add_run(text)
    set_font(run, size=sizes.get(level, 12), bold=True, color=colors.get(level, (0,0,0)))
    return p

def add_code_block(lines):
    for line in lines:
        p = doc.add_paragraph()
        p.paragraph_format.left_indent  = Inches(0.3)
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after  = Pt(1)
        run = p.add_run(line)
        set_font(run, size=9, mono=True, color=(50, 50, 50))
        # Light grey background via shading
        pPr = p._p.get_or_add_pPr()
        shd = OxmlElement('w:shd')
        shd.set(qn('w:val'),   'clear')
        shd.set(qn('w:color'), 'auto')
        shd.set(qn('w:fill'),  'F2F2F2')
        pPr.append(shd)

def add_table_from_md(header_row, rows):
    col_count = len(header_row)
    table = doc.add_table(rows=1 + len(rows), cols=col_count)
    table.style = 'Table Grid'
    # Header
    for i, cell_text in enumerate(header_row):
        cell = table.rows[0].cells[i]
        cell.text = cell_text
        run = cell.paragraphs[0].runs[0]
        set_font(run, bold=True, size=10, color=(255, 255, 255))
        # Blue header background
        tc   = cell._tc
        tcPr = tc.get_or_add_tcPr()
        shd  = OxmlElement('w:shd')
        shd.set(qn('w:val'),   'clear')
        shd.set(qn('w:color'), 'auto')
        shd.set(qn('w:fill'),  '2F5496')
        tcPr.append(shd)
    # Data rows
    for r_idx, row in enumerate(rows):
        for c_idx, cell_text in enumerate(row):
            cell = table.rows[r_idx + 1].cells[c_idx]
            cell.text = cell_text
            run = cell.paragraphs[0].runs[0] if cell.paragraphs[0].runs else cell.paragraphs[0].add_run(cell_text)
            set_font(run, size=10)
            if r_idx % 2 == 1:
                tc   = cell._tc
                tcPr = tc.get_or_add_tcPr()
                shd  = OxmlElement('w:shd')
                shd.set(qn('w:val'),   'clear')
                shd.set(qn('w:color'), 'auto')
                shd.set(qn('w:fill'),  'DCE6F1')
                tcPr.append(shd)
    doc.add_paragraph()

def inline_code_para(text):
    """Render a paragraph that may contain `inline code` spans."""
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(4)
    parts = re.split(r'`([^`]+)`', text)
    for i, part in enumerate(parts):
        if not part:
            continue
        run = p.add_run(part)
        if i % 2 == 1:  # inside backticks
            set_font(run, size=10, mono=True, color=(180, 0, 0))
        else:
            # handle **bold**
            bold_parts = re.split(r'\*\*([^*]+)\*\*', part)
            p.runs[-1].text = ''
            for j, bp in enumerate(bold_parts):
                r = p.add_run(bp)
                set_font(r, size=11, bold=(j % 2 == 1))
    return p

# ── Parse and render README ───────────────────────────────────
with open("README.md", encoding="utf-8") as f:
    content = f.read()

lines = content.splitlines()
i = 0
while i < len(lines):
    line = lines[i]

    # Headings
    if line.startswith("### "):
        add_heading(line[4:], 3); i += 1; continue
    if line.startswith("## "):
        add_heading(line[3:], 2); i += 1; continue
    if line.startswith("# "):
        add_heading(line[2:], 1); i += 1; continue

    # Fenced code block
    if line.startswith("```"):
        i += 1
        code_lines = []
        while i < len(lines) and not lines[i].startswith("```"):
            code_lines.append(lines[i])
            i += 1
        add_code_block(code_lines)
        i += 1; continue

    # Markdown table
    if line.startswith("|") and i + 1 < len(lines) and lines[i + 1].startswith("|---"):
        header = [c.strip() for c in line.strip("|").split("|")]
        i += 2  # skip separator
        rows = []
        while i < len(lines) and lines[i].startswith("|"):
            rows.append([c.strip() for c in lines[i].strip("|").split("|")])
            i += 1
        add_table_from_md(header, rows)
        continue

    # Bullet list
    if line.startswith("- ") or line.startswith("* "):
        p = doc.add_paragraph(style='List Bullet')
        p.paragraph_format.left_indent = Inches(0.3)
        text = line[2:]
        parts = re.split(r'\*\*([^*]+)\*\*', text)
        for j, part in enumerate(parts):
            run = p.add_run(part)
            set_font(run, size=11, bold=(j % 2 == 1))
        i += 1; continue

    # Horizontal rule
    if line.strip() in ("---", "***", "___"):
        p = doc.add_paragraph()
        pPr = p._p.get_or_add_pPr()
        pb  = OxmlElement('w:pBdr')
        bottom = OxmlElement('w:bottom')
        bottom.set(qn('w:val'),   'single')
        bottom.set(qn('w:sz'),    '6')
        bottom.set(qn('w:space'), '1')
        bottom.set(qn('w:color'), '4472C4')
        pb.append(bottom)
        pPr.append(pb)
        i += 1; continue

    # Normal paragraph (skip blank lines)
    if line.strip():
        inline_code_para(line.strip())
    else:
        doc.add_paragraph()

    i += 1

out = "TarotAI_Backend_Documentation.docx"
doc.save(out)
print(f"✅  Saved: {out}")
print("   → Upload this file to Google Drive, then open with Google Docs.")
