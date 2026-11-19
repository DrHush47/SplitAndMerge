"""
Battle-tested python-docx helper functions for routine mechanical .docx edits.

Each function encodes an empirical rule (R1-R12) discovered in real tests.
See SKILL.md for the full rule set and rationale.

Usage:
    from scripts.helpers import set_run_font, set_para_format, insert_heading_before, ...
"""

import re
from docx.shared import Pt, Mm, Cm
from docx.oxml.ns import qn, nsdecls
from docx.oxml import OxmlElement, parse_xml


# ── R5-compatible: font that survives Cyrillic ──────────────────────────────

def set_run_font(run, name="Times New Roman", size=12, bold=None, italic=None):
    """Set font on a run, including cs & eastAsia attributes (R5: critical for Cyrillic)."""
    run.font.name = name
    run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn('w:rFonts'))
    if rFonts is None:
        rFonts = OxmlElement('w:rFonts')
        rPr.insert(0, rFonts)
    for attr in ['w:ascii', 'w:hAnsi', 'w:cs', 'w:eastAsia']:
        rFonts.set(qn(attr), name)


# ── Paragraph & cell formatting ─────────────────────────────────────────────

def set_para_format(para, alignment=None, first_line_indent_cm=None,
                    line_spacing=None, bold=None,
                    font_name="Times New Roman", font_size=12):
    """Apply paragraph-level formatting and propagate font to all child runs."""
    if alignment is not None:
        para.alignment = alignment
    if first_line_indent_cm is not None:
        para.paragraph_format.first_line_indent = Cm(first_line_indent_cm)
    if line_spacing is not None:
        para.paragraph_format.line_spacing = line_spacing
    para.paragraph_format.space_after = Pt(0)
    para.paragraph_format.space_before = Pt(0)
    for run in para.runs:
        set_run_font(run, font_name, font_size, bold=bold)


def set_cell_format(cell, font_name="Times New Roman", font_size=12):
    """Apply table-cell formatting: zero indent, single spacing, font."""
    for para in cell.paragraphs:
        para.paragraph_format.first_line_indent = Cm(0)
        para.paragraph_format.line_spacing = 1.0
        para.paragraph_format.space_after = Pt(0)
        para.paragraph_format.space_before = Pt(0)
        for run in para.runs:
            set_run_font(run, font_name, font_size)


# ── Paragraph search (R2: text anchors, not hardcoded indexes) ──────────────

def find_para(doc, text_startswith=None, text_contains=None, text_equals=None):
    """Find a paragraph by text anchor. Returns (index, paragraph) or (None, None)."""
    for i, p in enumerate(doc.paragraphs):
        if text_startswith is not None and p.text.startswith(text_startswith):
            return i, p
        if text_contains is not None and text_contains in p.text:
            return i, p
        if text_equals is not None and text_equals.strip() == p.text.strip():
            return i, p
    return None, None


# ── Heading insertion (R4: check_duplicate=True always) ─────────────────────

def insert_heading_before(doc, anchor_text, heading_text, check_duplicate=True):
    """Insert a bold, centered, TNR-12pt heading before the anchor paragraph.

    Returns True if inserted, False if skipped (duplicate / missing anchor).
    """
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
    jc = OxmlElement('w:jc')
    jc.set(qn('w:val'), 'center')
    new_pPr.append(jc)
    new_p.append(new_pPr)

    new_r = OxmlElement('w:r')
    new_rPr = OxmlElement('w:rPr')
    rFonts = OxmlElement('w:rFonts')
    for attr in ['w:ascii', 'w:hAnsi', 'w:cs', 'w:eastAsia']:
        rFonts.set(qn(attr), 'Times New Roman')
    new_rPr.append(rFonts)
    sz = OxmlElement('w:sz')
    sz.set(qn('w:val'), '24')  # 12 pt
    new_rPr.append(sz)
    b = OxmlElement('w:b')
    new_rPr.append(b)
    new_r.append(new_rPr)
    t = OxmlElement('w:t')
    t.text = heading_text
    new_r.append(t)
    new_p.append(new_r)

    anchor._element.addprevious(new_p)
    print(f"  OK: heading '{heading_text}' inserted")
    return True


# ── End-of-document insertion (R10: do LAST among insertion edits) ──────────

def add_paragraph_safe(doc, text, check_duplicate_text=True):
    """Append a paragraph with duplicate guard.

    Returns True if added, False if skipped (duplicate detected).
    """
    if check_duplicate_text:
        first_line = text.split('\n')[0][:80]
        for p in doc.paragraphs:
            if first_line in p.text:
                print(f"  WARN: text block '{first_line}...' already exists — skipping (R10)")
                return False
    doc.add_paragraph(text)
    print("  OK: paragraph added to end")
    return True


# ── Cross-run text replacement (table cells, etc.) ──────────────────────────

def replace_cross_run_text(paragraph, old, new):
    """Replace a substring across run boundaries.

    WARNING: discards formatting of runs[1:].  Not suitable for paragraphs
    with heterogeneous formatting across runs.
    """
    if not paragraph.runs:
        return False
    full_text = paragraph.text
    if old not in full_text:
        return False
    new_text = full_text.replace(old, new)
    for run in paragraph.runs[1:]:
        run.text = ""
    paragraph.runs[0].text = new_text
    return True


def replace_cross_run_in_cell(cell, old, new):
    """Replace a substring in every paragraph of a table cell (cross-run aware)."""
    found = False
    for para in cell.paragraphs:
        if replace_cross_run_text(para, old, new):
            found = True
    return found


# ── Reference renumbering (R7 / R8 / R12) ───────────────────────────────────

def renumber_references(doc, start_patterns, stop_patterns):
    """Renumber references between start_patterns and stop_patterns as 1..N.

    start_patterns: list of header texts (e.g. ['ЛИТЕРАТУРА', 'REFERENCES']).
    stop_patterns:  list of EXPLICIT section markers (R12: never regex on body text).

    Strips existing numbering with regex '^\\s*\\d+\\.\\s*' before renumbering.
    Returns the number of references processed.
    """
    ref_start = None
    for i, p in enumerate(doc.paragraphs):
        txt = p.text.strip()
        for sp in start_patterns:
            if txt == sp:
                ref_start = i + 1
                break
        if ref_start is not None:
            break

    if ref_start is None:
        print(f"  WARN: no start header among {start_patterns}")
        return 0

    n = 1
    for i in range(ref_start, len(doc.paragraphs)):
        p = doc.paragraphs[i]
        txt = p.text.strip()
        if not txt:
            continue
        if txt in stop_patterns:
            break
        cleaned = re.sub(r'^\s*\d+\.\s*', '', txt)
        new_text = f"{n}. {cleaned}"
        for run in p.runs[1:]:
            run.text = ""
        if p.runs:
            p.runs[0].text = new_text
        else:
            p.text = new_text
        n += 1

    return n - 1


# ── Trailing cleanup ────────────────────────────────────────────────────────

def remove_trailing_empty_paragraphs(doc, keep_max=1):
    """Delete consecutive empty paragraphs at the end of the document.

    keep_max: number of trailing empty paragraphs to preserve (default 1).
    Returns the number of paragraphs removed.
    """
    last_non_empty = -1
    for i, p in enumerate(doc.paragraphs):
        if p.text.strip():
            last_non_empty = i

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


# ── Table layout helpers (cantSplit / tblHeader / fixed widths) ─────────────

def set_row_cant_split(row):
    """Prevent a table row from splitting across a page break (w:cantSplit)."""
    trPr = row._tr.get_or_add_trPr()
    if trPr.find(qn('w:cantSplit')) is None:
        trPr.append(OxmlElement('w:cantSplit'))


def set_row_header(row):
    """Repeat a table header row at the top of each new page (w:tblHeader)."""
    trPr = row._tr.get_or_add_trPr()
    if trPr.find(qn('w:tblHeader')) is None:
        trPr.append(OxmlElement('w:tblHeader'))


def set_table_col_widths(table, widths_mm):
    """Set fixed column widths in mm via w:tblLayout=fixed + w:tblGrid + gridSpan sum for merged cells.

    Validates positive widths and logical column count per row (including gridSpan/gridBefore/gridAfter).
    Horizontally merged cells (w:gridSpan > 1) get w:tcW equal to the sum of covered grid columns.
    """
    if (
        not widths_mm
        or any(not isinstance(w, (int, float)) or isinstance(w, bool) or w <= 0 for w in widths_mm)
    ):
        raise ValueError(f"widths_mm must be a non-empty sequence of positive numbers, got: {widths_mm!r}")

    expected_cols = len(widths_mm)
    dxa_widths = [round(w * 56.6929) for w in widths_mm]
    trs = table._tbl.findall(qn('w:tr'))

    row_meta = []
    for row_idx, tr in enumerate(trs):
        trPr = tr.find(qn('w:trPr'))
        grid_before = 0
        grid_after = 0
        if trPr is not None:
            gb = trPr.find(qn('w:gridBefore'))
            if gb is not None:
                grid_before = int(gb.get(qn('w:val'), '0'))
            ga = trPr.find(qn('w:gridAfter'))
            if ga is not None:
                grid_after = int(ga.get(qn('w:val'), '0'))
        tcs = tr.findall(qn('w:tc'))
        spans = []
        for tc in tcs:
            tcPr = tc.find(qn('w:tcPr'))
            gs = tcPr.find(qn('w:gridSpan')) if tcPr is not None else None
            spans.append(int(gs.get(qn('w:val'), '1')) if gs is not None else 1)
        row_cols = grid_before + sum(spans) + grid_after
        if row_cols != expected_cols:
            raise ValueError(
                f"Row {row_idx} has {row_cols} logical columns, expected len(widths_mm)={expected_cols}"
            )
        row_meta.append((tcs, spans, grid_before))

    table.autofit = False
    tblPr = table._tbl.tblPr

    tblW = tblPr.find(qn('w:tblW'))
    if tblW is None:
        tblW = OxmlElement('w:tblW')
        tblStyle = tblPr.find(qn('w:tblStyle'))
        if tblStyle is not None:
            tblStyle.addnext(tblW)
        else:
            tblPr.insert(0, tblW)
    tblW.set(qn('w:w'), str(sum(dxa_widths)))
    tblW.set(qn('w:type'), 'dxa')

    old_layout = tblPr.find(qn('w:tblLayout'))
    if old_layout is not None:
        tblPr.remove(old_layout)
    tblPr.append(parse_xml(f'<w:tblLayout {nsdecls("w")} w:type="fixed"/>'))

    old_grid = table._tbl.find(qn('w:tblGrid'))
    if old_grid is not None:
        table._tbl.remove(old_grid)
    new_grid = OxmlElement('w:tblGrid')
    for dxa in dxa_widths:
        gc = OxmlElement('w:gridCol')
        gc.set(qn('w:w'), str(dxa))
        new_grid.append(gc)
    tblPr.addnext(new_grid)

    for tcs, spans, grid_before in row_meta:
        col_idx = grid_before
        for tc, span in zip(tcs, spans):
            tcPr = tc.get_or_add_tcPr()
            span_dxa = sum(dxa_widths[col_idx : col_idx + span])
            tcW = tcPr.find(qn('w:tcW'))
            if tcW is None:
                tcW = OxmlElement('w:tcW')
                tcPr.append(tcW)
            tcW.set(qn('w:w'), str(span_dxa))
            tcW.set(qn('w:type'), 'dxa')
            col_idx += span


def check_pdf_page_breaks(docx_path, out_pdf_dir=None, orphan_chars=150, timeout=60):
    """Optional Stage 8 page-boundary check: export .docx -> PDF (isolated temp dir) and inspect via pypdf.

    Modes:
      1. Automatic heuristic: flags a low-text final page (< orphan_chars chars — possible orphan signature/row).
      2. Diagnostic output: prints char count, start and end snippets per page for manual review + saves PDF.

    Never reads a stale PDF from an earlier run on export failure; catches converter errors, timeouts, and PDF parse errors.
    Returns structured dict with status in {'ok', 'skipped', 'export_failed', 'parse_failed'}.
    """
    from pathlib import Path
    import shutil
    import subprocess
    import tempfile

    src = Path(docx_path).resolve()
    if not src.is_file():
        msg = f"Source DOCX not found: {src}"
        print(f"  EXPORT_FAILED PDF check ({src.name}): {msg}")
        return {
            "status": "export_failed", "converter": None, "pdf_path": None,
            "pages": [], "warnings": [], "error": msg,
        }

    pdf_dir = Path(out_pdf_dir).resolve() if out_pdf_dir else src.parent / "_pdf_check"
    final_pdf = pdf_dir / (src.stem + ".pdf")

    attempted = []
    errors = []
    used_converter = None

    with tempfile.TemporaryDirectory(prefix="docx_pdf_check_") as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        tmp_pdf = tmp_dir / (src.stem + ".pdf")

        try:
            import win32com.client as _win32com_client  # type: ignore
        except ImportError:
            _win32com_client = None

        if _win32com_client is not None:
            attempted.append("word_com")
            word = None
            try:
                word = _win32com_client.Dispatch("Word.Application")
                word.Visible = False
                word.DisplayAlerts = 0
                d = word.Documents.Open(str(src), ReadOnly=True)
                try:
                    d.SaveAs2(str(tmp_pdf), FileFormat=17)
                finally:
                    d.Close(False)
                if tmp_pdf.is_file() and tmp_pdf.stat().st_size > 0:
                    used_converter = "word_com"
                else:
                    errors.append("word_com: produced missing or empty PDF")
            except Exception as exc:
                errors.append(f"word_com: {type(exc).__name__}: {exc}")
            finally:
                if word is not None:
                    try:
                        word.Quit()
                    except Exception:
                        pass

        if used_converter is None:
            soffice = shutil.which("soffice") or shutil.which("libreoffice")
            if soffice:
                attempted.append("libreoffice")
                try:
                    proc = subprocess.run(
                        [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(tmp_dir), str(src)],
                        check=False, capture_output=True, text=True, timeout=timeout,
                    )
                    if proc.returncode == 0 and tmp_pdf.is_file() and tmp_pdf.stat().st_size > 0:
                        used_converter = "libreoffice"
                    else:
                        detail_out = (proc.stderr or proc.stdout or "").strip()[:200]
                        errors.append(
                            f"libreoffice rc={proc.returncode}"
                            + (f": {detail_out}" if detail_out else " (missing or empty PDF)")
                        )
                except subprocess.TimeoutExpired:
                    errors.append(f"libreoffice: timeout ({timeout}s)")
                except OSError as exc:
                    errors.append(f"libreoffice: {type(exc).__name__}: {exc}")

        if used_converter is None:
            if not attempted:
                msg = "neither Word COM (pywin32) nor LibreOffice (soffice) is installed"
                print(f"  SKIP PDF check ({src.name}): {msg}")
                return {
                    "status": "skipped", "converter": None, "pdf_path": None,
                    "pages": [], "warnings": [], "error": msg,
                }
            msg = "; ".join(errors) or "PDF export failed"
            print(f"  EXPORT_FAILED PDF check ({src.name}): {msg}")
            return {
                "status": "export_failed", "converter": None, "pdf_path": None,
                "pages": [], "warnings": [], "error": msg,
            }

        pdf_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tmp_pdf, final_pdf)

    try:
        import pypdf
    except ImportError:
        msg = "pypdf not installed (included in profile lite)"
        print(f"  SKIP PDF check ({final_pdf.name}): {msg}")
        return {
            "status": "skipped", "converter": used_converter, "pdf_path": str(final_pdf),
            "pages": [], "warnings": [], "error": msg,
        }

    try:
        reader = pypdf.PdfReader(str(final_pdf))
        pages_info = []
        for idx, page in enumerate(reader.pages, start=1):
            txt = re.sub(r'\s+', ' ', (page.extract_text() or '')).strip()
            pages_info.append({"page": idx, "chars": len(txt), "start": txt[:80], "end": txt[-80:]})
            print(f"  Page {idx} ({len(txt)} chars): {txt[:60]!r} ... {txt[-60:]!r}")
    except Exception as exc:
        msg = f"{type(exc).__name__}: {exc}"
        print(f"  PARSE_FAILED PDF check ({final_pdf.name}): {msg}")
        return {
            "status": "parse_failed", "converter": used_converter, "pdf_path": str(final_pdf),
            "pages": [], "warnings": [], "error": msg,
        }

    warnings = []
    if len(pages_info) > 1 and pages_info[-1]["chars"] < orphan_chars:
        w = (
            f"last page {len(pages_info)} has only {pages_info[-1]['chars']} chars "
            f"(< {orphan_chars}) — possible orphan signature/row (verify visually)"
        )
        warnings.append(w)
        print(f"  WARN: {w}")

    return {
        "status": "ok",
        "converter": used_converter,
        "pdf_path": str(final_pdf),
        "pages": pages_info,
        "warnings": warnings,
        "error": None,
    }
