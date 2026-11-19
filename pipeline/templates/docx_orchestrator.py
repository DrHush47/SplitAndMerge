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
    """Зафиксировать ширины столбцов таблицы (w:tblLayout=fixed + w:tblGrid + сумма gridSpan для объединённых ячеек).

    Проверяет положительность ширин и соответствие len(widths_mm) логическому числу столбцов каждой строки.
    Для горизонтально объединённых ячеек (w:gridSpan > 1) выставляет w:tcW равным сумме покрываемых колонок.
    """
    if (
        not widths_mm
        or any(not isinstance(w, (int, float)) or isinstance(w, bool) or w <= 0 for w in widths_mm)
    ):
        raise ValueError(f"widths_mm должен быть непустой последовательностью чисел > 0, получено: {widths_mm!r}")

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
                f"Строка {row_idx} содержит {row_cols} логических столбцов, а len(widths_mm)={expected_cols}"
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


_WORD_COM_EXPORT_SNIPPET = """
import sys
import win32com.client
word = win32com.client.Dispatch("Word.Application")
word.Visible = False
word.DisplayAlerts = 0
try:
    d = word.Documents.Open(sys.argv[1], ReadOnly=True)
    try:
        d.SaveAs2(sys.argv[2], FileFormat=17)
    finally:
        d.Close(False)
finally:
    word.Quit()
"""


def check_pdf_page_breaks(docx_path, out_pdf_dir=None, orphan_chars=150, timeout=60):
    """Опциональный контроль границ страниц (Этап 8): экспорт .docx → PDF и анализ через pypdf.

    Режимы работы:
      1. Автоматическая эвристика: предупреждение (WARN) при малотекстовой последней странице
         (< orphan_chars символов — частый признак оторвавшейся подписи/строки, требует проверки).
      2. Диагностический вывод: печать числа символов, начала и конца текста каждой страницы
         для ручной оценки разрывов страниц и сохранённый PDF для визуального контроля.

    Гарантии изоляции и обработки ошибок:
      - Word COM и LibreOffice пишут в раздельные подкаталоги внутри TemporaryDirectory
        (артефакты одного конвертера не мешают другому; старый PDF из прошлых запусков не читается).
      - Оба конвертера запускаются в отдельном процессе с ограничением timeout (для Word COM
        таймаут ограничивает ожидание Python-процесса; при жёстком зависании DCOM сам процесс
        WINWORD.EXE на Windows может потребовать ручного завершения).
      - Чтение и разбор через pypdf выполняются на временном PDF ДО публикации в out_pdf_dir;
        повреждённый PDF не перезаписывает прежний результат.
      - Ошибки сохранения (OSError при mkdir/copy2, напр. открытый в просмотрщике файл)
        перехватываются и возвращают статус "save_failed" с уже собранными pages/warnings.

    Возвращает структурированный dict:
      {
        "status": "ok" | "skipped" | "export_failed" | "parse_failed" | "save_failed",
        "converter": "word_com" | "libreoffice" | None,
        "pdf_path": str | None,
        "pages": [{"page": int, "chars": int, "start": str, "end": str}, ...],
        "warnings": [str, ...],
        "error": str | None,
      }
    """
    from pathlib import Path
    import shutil as _shutil
    import subprocess
    import sys as _sys
    import tempfile

    src = Path(docx_path).resolve()
    if not src.is_file():
        msg = f"Исходный DOCX не найден: {src}"
        print(f"EXPORT_FAILED PDF-проверка ({src.name}): {msg}")
        return {
            "status": "export_failed", "converter": None, "pdf_path": None,
            "pages": [], "warnings": [], "error": msg,
        }

    pdf_dir = Path(out_pdf_dir).resolve() if out_pdf_dir else src.parent / "_pdf_check"
    final_pdf = pdf_dir / (src.stem + ".pdf")

    attempted = []
    errors = []
    used_converter = None
    exported_pdf = None

    with tempfile.TemporaryDirectory(prefix="docx_pdf_check_") as tmp_root_str:
        tmp_root = Path(tmp_root_str)

        # 1. MS Word COM в отдельном процессе и изолированном подкаталоге (Windows + pywin32)
        try:
            import win32com.client as _win32com_client  # type: ignore
        except ImportError:
            _win32com_client = None

        if _win32com_client is not None:
            attempted.append("word_com")
            word_dir = tmp_root / "word"
            word_dir.mkdir()
            word_pdf = word_dir / (src.stem + ".pdf")
            try:
                proc = subprocess.run(
                    [_sys.executable, "-c", _WORD_COM_EXPORT_SNIPPET, str(src), str(word_pdf)],
                    check=False, capture_output=True, text=True, timeout=timeout,
                )
                if proc.returncode == 0 and word_pdf.is_file() and word_pdf.stat().st_size > 0:
                    used_converter = "word_com"
                    exported_pdf = word_pdf
                else:
                    detail_out = (proc.stderr or proc.stdout or "").strip()[:200]
                    errors.append(
                        f"word_com rc={proc.returncode}"
                        + (f": {detail_out}" if detail_out else " (PDF не создан или пуст)")
                    )
            except subprocess.TimeoutExpired:
                errors.append(f"word_com: timeout ({timeout}s)")
            except OSError as exc:
                errors.append(f"word_com: {type(exc).__name__}: {exc}")

        # 2. Fallback: LibreOffice (soffice --headless) в свой изолированный подкаталог
        if used_converter is None:
            soffice = _shutil.which("soffice") or _shutil.which("libreoffice")
            if soffice:
                attempted.append("libreoffice")
                lo_dir = tmp_root / "libreoffice"
                lo_dir.mkdir()
                lo_pdf = lo_dir / (src.stem + ".pdf")
                try:
                    proc = subprocess.run(
                        [soffice, "--headless", "--convert-to", "pdf", "--outdir", str(lo_dir), str(src)],
                        check=False, capture_output=True, text=True, timeout=timeout,
                    )
                    if proc.returncode == 0 and lo_pdf.is_file() and lo_pdf.stat().st_size > 0:
                        used_converter = "libreoffice"
                        exported_pdf = lo_pdf
                    else:
                        detail_out = (proc.stderr or proc.stdout or "").strip()[:200]
                        errors.append(
                            f"libreoffice rc={proc.returncode}"
                            + (f": {detail_out}" if detail_out else " (PDF не создан или пуст)")
                        )
                except subprocess.TimeoutExpired:
                    errors.append(f"libreoffice: timeout ({timeout}s)")
                except OSError as exc:
                    errors.append(f"libreoffice: {type(exc).__name__}: {exc}")

        if used_converter is None or exported_pdf is None:
            if not attempted:
                msg = "не найден Word COM (pywin32) или LibreOffice (soffice)"
                print(f"SKIP PDF-проверка ({src.name}): {msg}")
                return {
                    "status": "skipped", "converter": None, "pdf_path": None,
                    "pages": [], "warnings": [], "error": msg,
                }
            msg = "; ".join(errors) or "ошибка конвертации PDF"
            print(f"EXPORT_FAILED PDF-проверка ({src.name}): {msg}")
            return {
                "status": "export_failed", "converter": None, "pdf_path": None,
                "pages": [], "warnings": [], "error": msg,
            }

        # 3. Анализируем временный PDF ДО публикации в out_pdf_dir
        try:
            import pypdf
        except ImportError:
            saved_path = None
            try:
                pdf_dir.mkdir(parents=True, exist_ok=True)
                _shutil.copy2(exported_pdf, final_pdf)
                saved_path = str(final_pdf)
            except OSError as exc:
                msg = f"pypdf не установлен; сохранить PDF в {final_pdf} также не удалось: {exc}"
                print(f"SAVE_FAILED PDF-проверка ({src.name}): {msg}")
                return {
                    "status": "save_failed", "converter": used_converter, "pdf_path": None,
                    "pages": [], "warnings": [], "error": msg,
                }
            msg = "pypdf не установлен (входит в профиль lite)"
            print(f"SKIP PDF-анализ ({final_pdf.name}): {msg}")
            return {
                "status": "skipped", "converter": used_converter, "pdf_path": saved_path,
                "pages": [], "warnings": [], "error": msg,
            }

        try:
            reader = pypdf.PdfReader(str(exported_pdf))
            pages_info = []
            for idx, page in enumerate(reader.pages, start=1):
                txt = re.sub(r'\s+', ' ', (page.extract_text() or '')).strip()
                pages_info.append({"page": idx, "chars": len(txt), "start": txt[:80], "end": txt[-80:]})
                print(f"  Стр.{idx} ({len(txt)} симв.): {txt[:60]!r} ... {txt[-60:]!r}")
        except Exception as exc:
            msg = f"{type(exc).__name__}: {exc}"
            print(f"PARSE_FAILED PDF-анализ ({src.name}): {msg}")
            return {
                "status": "parse_failed", "converter": used_converter, "pdf_path": None,
                "pages": [], "warnings": [], "error": msg,
            }

        warnings = []
        if len(pages_info) > 1 and pages_info[-1]["chars"] < orphan_chars:
            w = (
                f"последняя страница {len(pages_info)} содержит лишь {pages_info[-1]['chars']} симв. "
                f"(< {orphan_chars}) — возможна оторвавшаяся подпись или строка (проверить глазами)"
            )
            warnings.append(w)
            print(f"  WARN: {w}")

        # 4. Публикуем проверенный PDF в out_pdf_dir (с защитой от OSError/PermissionError)
        try:
            pdf_dir.mkdir(parents=True, exist_ok=True)
            _shutil.copy2(exported_pdf, final_pdf)
        except OSError as exc:
            msg = f"Не удалось сохранить PDF в {final_pdf}: {exc}"
            print(f"SAVE_FAILED PDF-проверка ({src.name}): {msg}")
            return {
                "status": "save_failed",
                "converter": used_converter,
                "pdf_path": None,
                "pages": pages_info,
                "warnings": warnings,
                "error": msg,
            }

    return {
        "status": "ok",
        "converter": used_converter,
        "pdf_path": str(final_pdf),
        "pages": pages_info,
        "warnings": warnings,
        "error": None,
    }


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
