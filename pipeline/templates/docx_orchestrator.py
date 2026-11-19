#!/usr/bin/env python3
"""Оркестратор правок .docx через python-docx (канон §4 docx-protocol.md)."""
import re
import shutil
from docx import Document
from docx.shared import Pt, Mm, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn, nsdecls
from docx.oxml import OxmlElement, parse_xml

FILE = "результат.docx"


def set_run_font(run, name="Times New Roman", size=12, bold=None, italic=None):
    """Установить шрифт run (включая cs и eastAsia)."""
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
        rPr.append(rFonts)
    for attr in ['w:ascii', 'w:hAnsi', 'w:cs', 'w:eastAsia']:
        rFonts.set(qn(attr), name)


def set_para_format(para, alignment=None, first_line_indent_cm=None,
                    line_spacing=None, bold=None, font_name="Times New Roman", font_size=12):
    """Установить формат параграфа и всех его runs."""
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
    """Установить шрифт во всех параграфах ячейки таблицы."""
    for para in cell.paragraphs:
        para.paragraph_format.first_line_indent = Cm(0)
        para.paragraph_format.line_spacing = 1.0
        para.paragraph_format.space_after = Pt(0)
        para.paragraph_format.space_before = Pt(0)
        for run in para.runs:
            set_run_font(run, font_name, font_size)


def find_para(doc, text_startswith=None, text_contains=None):
    """Найти параграф по началу текста или содержимому."""
    for i, p in enumerate(doc.paragraphs):
        if text_startswith and p.text.startswith(text_startswith):
            return i, p
        if text_contains and text_contains in p.text:
            return i, p
    return None, None


def insert_heading_before(doc, anchor_text, heading_text, check_duplicate=True):
    """Вставить заголовок перед абзацем-якорем (см. §1.6 docx-protocol.md)."""
    if check_duplicate:
        for i, p in enumerate(doc.paragraphs):
            if heading_text.strip() in p.text:
                print(f"WARN: заголовок '{heading_text}' уже существует в P{i} — пропускаем вставку")
                return False
    _, anchor = find_para(doc, text_startswith=anchor_text)
    if anchor is None:
        print(f"WARN: якорь '{anchor_text}' не найден")
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
    sz.set(qn('w:val'), '24')
    new_rPr.append(sz)
    b = OxmlElement('w:b')
    new_rPr.append(b)
    new_r.append(new_rPr)
    t = OxmlElement('w:t')
    t.text = heading_text
    new_r.append(t)
    new_p.append(new_r)
    anchor._element.addprevious(new_p)
    return True


def replace_cross_run_text(paragraph, old, new):
    """Заменить подстроку в параграфе с учётом cross-run разбивки (см. §5.1)."""
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
    """Заменить подстроку во всех параграфах ячейки таблицы (cross-run aware)."""
    found = False
    for para in cell.paragraphs:
        if replace_cross_run_text(para, old, new):
            found = True
    return found


def renumber_references(doc, ref_start_pattern='ЛИТЕРАТУРА', ref_end_pattern='СВЕДЕНИЯ ОБ АВТОРАХ'):
    """Проставить нумерацию 1..N (см. §1.8: regex, не срезы строк)."""
    ref_start = None
    for i, p in enumerate(doc.paragraphs):
        if p.text.strip() == ref_start_pattern:
            ref_start = i + 1
            break
    if ref_start is None:
        print(f"WARN: заголовок '{ref_start_pattern}' не найден")
        return 0
    n = 1
    for i in range(ref_start, len(doc.paragraphs)):
        p = doc.paragraphs[i]
        txt = p.text.strip()
        if not txt:
            continue
        if txt == ref_end_pattern:
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


def set_row_cant_split(row):
    """Запретить разрыв строки таблицы между страницами (w:cantSplit)."""
    trPr = row._tr.get_or_add_trPr()
    if trPr.find(qn('w:cantSplit')) is None:
        trPr.append(OxmlElement('w:cantSplit'))


def set_row_header(row):
    """Повторять строку заголовка таблицы на каждой новой странице (w:tblHeader)."""
    trPr = row._tr.get_or_add_trPr()
    if trPr.find(qn('w:tblHeader')) is None:
        trPr.append(OxmlElement('w:tblHeader'))


def set_table_col_widths(table, widths_mm):
    """Зафиксировать ширины столбцов таблицы (w:tblLayout=fixed + w:tblGrid, с учётом gridSpan)."""
    table.autofit = False
    tblPr = table._tbl.tblPr
    old_layout = tblPr.find(qn('w:tblLayout'))
    if old_layout is not None:
        tblPr.remove(old_layout)
    tblPr.append(parse_xml(f'<w:tblLayout {nsdecls("w")} w:type="fixed"/>'))

    old_grid = table._tbl.find(qn('w:tblGrid'))
    if old_grid is not None:
        table._tbl.remove(old_grid)
    new_grid = OxmlElement('w:tblGrid')
    for w in widths_mm:
        gc = OxmlElement('w:gridCol')
        gc.set(qn('w:w'), str(int(round(w * 56.6929))))
        new_grid.append(gc)
    tblPr.addnext(new_grid)

    for row in table.rows:
        for ci, cell in enumerate(row.cells):
            if ci >= len(widths_mm):
                continue
            tcPr = cell._tc.get_or_add_tcPr()
            grid_span = tcPr.find(qn('w:gridSpan'))
            if grid_span is not None and int(grid_span.get(qn('w:val'), '1')) > 1:
                continue
            w_mm = widths_mm[ci]
            cell.width = Mm(w_mm)
            tcW = tcPr.find(qn('w:tcW'))
            if tcW is None:
                tcW = OxmlElement('w:tcW')
                tcPr.append(tcW)
            tcW.set(qn('w:w'), str(int(round(w_mm * 56.6929))))
            tcW.set(qn('w:type'), 'dxa')


def check_pdf_page_breaks(docx_path, out_pdf_dir=None, orphan_chars=150):
    """Опциональный контроль вёрстки (Этап 8): экспорт .docx → PDF и анализ разрывов страниц.

    Использует MS Word COM (Windows + pywin32) или LibreOffice (soffice --headless) + pypdf.
    При отсутствии конвертера или pypdf печатает SKIP и возвращает None (не падает).
    """
    from pathlib import Path
    import subprocess
    import shutil as _shutil

    src = Path(docx_path).resolve()
    pdf_dir = Path(out_pdf_dir).resolve() if out_pdf_dir else src.parent / "_pdf_check"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / (src.stem + ".pdf")

    exported = False
    try:
        import win32com.client  # type: ignore
        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        try:
            d = word.Documents.Open(str(src), ReadOnly=True)
            d.SaveAs2(str(pdf_path), FileFormat=17)  # wdFormatPDF
            d.Close(False)
            exported = pdf_path.is_file()
        finally:
            word.Quit()
    except Exception:
        soffice = _shutil.which("soffice") or _shutil.which("libreoffice")
        if soffice:
            subprocess.run(
                [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(pdf_dir), str(src)],
                check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60,
            )
            exported = pdf_path.is_file()

    if not exported:
        print(f"SKIP PDF-проверка ({src.name}): не найден Word COM (pywin32) или LibreOffice")
        return None

    try:
        import pypdf
    except ImportError:
        print(f"SKIP PDF-анализ ({pdf_path.name}): pypdf не установлен (входит в профиль lite)")
        return None

    reader = pypdf.PdfReader(str(pdf_path))
    pages_info = []
    for idx, page in enumerate(reader.pages, start=1):
        txt = re.sub(r'\s+', ' ', (page.extract_text() or '')).strip()
        pages_info.append({"page": idx, "chars": len(txt), "start": txt[:80], "end": txt[-80:]})
        print(f"  Стр.{idx} ({len(txt)} симв.): {txt[:60]!r} ... {txt[-60:]!r}")
    if len(pages_info) > 1 and pages_info[-1]["chars"] < orphan_chars:
        print(f"  WARN: последняя страница {len(pages_info)} содержит лишь {pages_info[-1]['chars']} симв. — вероятна оторвавшаяся подпись/строка")
    return pages_info


if __name__ == "__main__":
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else "исходник.docx"
    out = sys.argv[2] if len(sys.argv) > 2 else FILE
    shutil.copy(src, out)
    doc = Document(out)
    for section in doc.sections:
        section.top_margin = Mm(25)
        section.bottom_margin = Mm(25)
        section.left_margin = Mm(25)
        section.right_margin = Mm(25)
    for para in doc.paragraphs:
        set_para_format(para, line_spacing=1.0, first_line_indent_cm=1.25, font_size=12)
    doc.save(out)
    print(f"Сохранено: {out}")
