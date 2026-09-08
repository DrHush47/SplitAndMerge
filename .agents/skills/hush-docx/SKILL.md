---
name: hush-docx
description: "Use for ALL routine mechanical edits to existing .docx: formatting, heading insertion, table cell replacements, reference renumbering, text insertion, italic/bold, trailing cleanup. Uses python-docx exclusively — one script, all edits, one shot. Do NOT use for creating new docs, tracked changes/XML, or .doc conversion."
---
# FreeBuffdocx — Routine docx Edits via python-docx

## Overview

**One tool, one script, one shot.** Battle-tested across 6 documents: 10/10 edits in 0.065 seconds average. Each rule below came from a real bug in a real test — see Empirical Track Record at the bottom.

## Quick Decision Tree

| Task | Approach |
|------|----------|
| Global formatting (font, margins, spacing, indent) | Iterate `doc.paragraphs` + `doc.sections` + `table.rows→cells` |
| Insert heading before a paragraph | `insert_heading_before()` with `check_duplicate=True` |
| Replace text in table cell | Text-based search + `replace_cross_run_in_cell()` |
| Renumber reference list | `renumber_references()` with start/stop patterns (explicit markers only) |
| Expand abbreviation at first mention | Regex pattern covering ALL grammatical cases (R9) |
| Add text to end of document | `add_paragraph_safe()` with duplicate check — do LAST in script (R10) |
| Set italic/bold | `run.italic = True` / `run.bold = True` |
| Replace inline subtitle with proper heading | Check if separate heading exists → if yes WARN; if no, convert paragraph + `addnext()` (R11) |
| Remove trailing empty paragraphs | Find last non-empty → delete everything after `keep_max` |

## Mandatory Rules

**R1: Reconnaissance first.** Read the document via python-docx before any edit — paragraph count, table structure, key text anchors. Indexes shift on insert/delete; knowing structure upfront prevents half the bugs.

**R2: Text anchors, not hardcoded indexes.** Use `find_para(text_startswith="...")` — never `doc.paragraphs[42]`.

**R3: WARN, don't exit.** Non-critical failures get `print("WARN: ...")`. Only exit on data loss (paragraph count decreased, table disappeared, file won't open).

**R4: Check duplicates before inserting.** Always verify a heading/text doesn't already exist. `insert_heading_before(check_duplicate=True)` handles this.

**R5: Unicode fix at the top of EVERY script.**
```python
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
```
Or run with `PYTHONUTF8=1 python script.py`.

**R6: Max 2 iterations.** Fix script once, re-run. If still issues after second run: deliver file + list remaining problems.

**R7: Regex for numbering validation.** `re.match(r'^\d+\.\s', txt)` — never `txt[1:3] == ". "` (misses 10..27).

**R8: Cross-reference markers with reconnaissance.** Docs may say "REFERENCES" not "ЛИТЕРАТУРА". Always pass lists of variants.

**R9: Abbreviation expansion — check ALL grammatical cases.** Use regex for all 6 Russian cases.

**R10: Insert end-of-document blocks LAST.** Put `[TEXT-6]` block as the LAST insertion edit.

**R11: Inline subtitle replacement — NEVER use `p.text.replace()`.** Convert paragraph to heading + use `addnext()` for body text.

**R12: Stop-conditions for reference renumbering — be specific.** Use only explicit section markers as stop patterns, not regex on text content.

## Helper Functions

```python
from docx.shared import Pt, Mm, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import re

def set_run_font(run, name="Times New Roman", size=12, bold=None, italic=None):
    run.font.name = name
    run.font.size = Pt(size)
    if bold is not None: run.bold = bold
    if italic is not None: run.italic = italic
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn('w:rFonts'))
    if rFonts is None:
        rFonts = OxmlElement('w:rFonts')
        rPr.insert(0, rFonts)
    for attr in ['w:ascii', 'w:hAnsi', 'w:cs', 'w:eastAsia']:
        rFonts.set(qn(attr), name)

def set_para_format(para, alignment=None, first_line_indent_cm=None,
                    line_spacing=None, bold=None, font_name="Times New Roman", font_size=12):
    if alignment is not None: para.alignment = alignment
    if first_line_indent_cm is not None:
        para.paragraph_format.first_line_indent = Cm(first_line_indent_cm)
    if line_spacing is not None:
        para.paragraph_format.line_spacing = line_spacing
    para.paragraph_format.space_after = Pt(0)
    para.paragraph_format.space_before = Pt(0)
    for run in para.runs:
        set_run_font(run, font_name, font_size, bold=bold)

def set_cell_format(cell, font_name="Times New Roman", font_size=12):
    for para in cell.paragraphs:
        para.paragraph_format.first_line_indent = Cm(0)
        para.paragraph_format.line_spacing = 1.0
        para.paragraph_format.space_after = Pt(0)
        para.paragraph_format.space_before = Pt(0)
        for run in para.runs:
            set_run_font(run, font_name, font_size)

def find_para(doc, text_startswith=None, text_contains=None, text_equals=None):
    for i, p in enumerate(doc.paragraphs):
        if text_startswith is not None and p.text.startswith(text_startswith): return i, p
        if text_contains is not None and text_contains in p.text: return i, p
        if text_equals is not None and text_equals.strip() == p.text.strip(): return i, p
    return None, None

def insert_heading_before(doc, anchor_text, heading_text, check_duplicate=True):
    if check_duplicate:
        for i, p in enumerate(doc.paragraphs):
            if heading_text.strip() in p.text:
                print(f"  WARN: '{heading_text}' already exists at P{i} — skipping (R4)")
                return False
    _, anchor = find_para(doc, text_startswith=anchor_text)
    if anchor is None:
        print(f"  WARN: anchor '{anchor_text}' not found — skipping (R2)")
        return False
    new_p = OxmlElement('w:p')
    new_pPr = OxmlElement('w:pPr')
    jc = OxmlElement('w:jc'); jc.set(qn('w:val'), 'center'); new_pPr.append(jc)
    new_p.append(new_pPr)
    new_r = OxmlElement('w:r')
    new_rPr = OxmlElement('w:rPr')
    rFonts = OxmlElement('w:rFonts')
    for attr in ['w:ascii', 'w:hAnsi', 'w:cs', 'w:eastAsia']: rFonts.set(qn(attr), 'Times New Roman')
    new_rPr.append(rFonts)
    sz = OxmlElement('w:sz'); sz.set(qn('w:val'), '24'); new_rPr.append(sz)
    b = OxmlElement('w:b'); new_rPr.append(b)
    new_r.append(new_rPr)
    t = OxmlElement('w:t'); t.text = heading_text; new_r.append(t)
    new_p.append(new_r)
    anchor._element.addprevious(new_p)
    print(f"  OK: heading '{heading_text}' inserted")
    return True

def add_paragraph_safe(doc, text, check_duplicate_text=True):
    if check_duplicate_text:
        first_line = text.split('\n')[0][:80]
        for p in doc.paragraphs:
            if first_line in p.text:
                print(f"  WARN: text block '{first_line}...' already exists — skipping (R10)")
                return False
    doc.add_paragraph(text)
    print(f"  OK: paragraph added to end")
    return True

def replace_cross_run_text(paragraph, old, new):
    if not paragraph.runs: return False
    full_text = paragraph.text
    if old not in full_text: return False
    new_text = full_text.replace(old, new)
    for run in paragraph.runs[1:]: run.text = ""
    paragraph.runs[0].text = new_text
    return True

def replace_cross_run_in_cell(cell, old, new):
    found = False
    for para in cell.paragraphs:
        if replace_cross_run_text(para, old, new): found = True
    return found

def renumber_references(doc, start_patterns, stop_patterns):
    ref_start = None
    for i, p in enumerate(doc.paragraphs):
        txt = p.text.strip()
        for sp in start_patterns:
            if txt == sp: ref_start = i + 1; break
        if ref_start: break
    if ref_start is None:
        print(f"  WARN: no start header among {start_patterns}")
        return 0
    n = 1
    for i in range(ref_start, len(doc.paragraphs)):
        p = doc.paragraphs[i]
        txt = p.text.strip()
        if not txt: continue
        if txt in stop_patterns: break
        cleaned = re.sub(r'^\s*\d+\.\s*', '', txt)
        new_text = f"{n}. {cleaned}"
        for run in p.runs[1:]: run.text = ""
        if p.runs: p.runs[0].text = new_text
        else: p.text = new_text
        n += 1
    return n - 1

def remove_trailing_empty_paragraphs(doc, keep_max=1):
    last_non_empty = -1
    for i, p in enumerate(doc.paragraphs):
        if p.text.strip(): last_non_empty = i
    to_remove = []
    keep_count = 0
    for i in range(len(doc.paragraphs) - 1, last_non_empty, -1):
        if not doc.paragraphs[i].text.strip():
            if keep_count < keep_max:
                keep_count += 1
            else:
                to_remove.append(doc.paragraphs[i]._element)
    for el in to_remove:
        el.getparent().remove(el)
    print(f"  OK: removed {len(to_remove)} trailing empty paragraphs (kept {keep_count})")
    return len(to_remove)
```

## Scripts

| File | Purpose |
|------|---------|
| `scripts/helpers.py` | All 10 helper functions as an importable module |
| `scripts/orchestrator_template.py` | Drop-in starting point |
| `scripts/validate_edits.py` | Standalone validator |
| `scripts/__init__.py` | Package marker |

## Quick start
```bash
cp scripts/orchestrator_template.py my_edits.py
PYTHONUTF8=1 python my_edits.py
PYTHONUTF8=1 python scripts/validate_edits.py result.docx source.docx
```

## Dependencies

- `pip install python-docx` (MIT)
- Python 3.8+

## Empirical Track Record

| Date | Test | Document | Edits | Result | Lesson → Rule |
|---|---|---|---|---|---|
| 2026-07-14 | v1 strategy | test_strategy_v1.docx | 8 | 7/8 | → R4 |
| 2026-07-14 | v2 apply | доклад12_v2.docx | 8 | 7/8 | → R10, R9 |
| 2026-07-15 | v3 final | доклад12_v3.docx | 10 | 10/10 | confirmed R4,R5,R7,R8 |
| 2026-07-15 | Anthropic | доклад10_anthropic.docx | 12 | 11/12 | → R11, R12, R10 |
| 2026-07-18 | Desktop | доклад12_desktop.docx | 10 | 10/10 | → R9 fully |
| 2026-07-18 | DesktopSkill | FreeBuffDesktopSkill.docx | 10 | 10/10 | all R1-R12 |
| 2026-07-19 | MiniMaxM3 | доклад12.docx | 10 | 10/10 | 0.048s |
| 2026-07-19 | structural | доклад12_structural.docx | 8 | 8/8 | new class of tasks |
