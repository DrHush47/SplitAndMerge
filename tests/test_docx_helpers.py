#!/usr/bin/env python3
"""Тесты табличных хелперов и PDF page-break контроля в docx_orchestrator и hush-docx."""

import importlib.util
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

docx = pytest.importorskip("docx")
from docx.oxml.ns import qn  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

MODULE_PATHS = [
    "pipeline/templates/docx_orchestrator.py",
    ".agents/skills/hush-docx/scripts/helpers.py",
]


def _load_module(name: str, rel_path: str):
    path = REPO_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("rel_path", MODULE_PATHS)
def test_table_layout_helpers_ooxml_and_gridspan_sums(rel_path):
    """set_table_col_widths согласует w:tcW объединённых ячеек с суммой покрываемых колонок."""
    mod = _load_module("docx_mod", rel_path)
    doc = docx.Document()
    table = doc.add_table(rows=4, cols=3)

    # Идемпотентность cantSplit и tblHeader
    mod.set_row_header(table.rows[0])
    mod.set_row_header(table.rows[0])
    mod.set_row_cant_split(table.rows[1])
    mod.set_row_cant_split(table.rows[1])

    assert len(table.rows[0]._tr.trPr.findall(qn("w:tblHeader"))) == 1
    assert len(table.rows[1]._tr.trPr.findall(qn("w:cantSplit"))) == 1

    # Строка 2: полное объединение всех 3 колонок (gridSpan=3)
    table.rows[2].cells[0].merge(table.rows[2].cells[2])
    # Строка 3: частичное объединение колонок 1..2 (gridSpan=2)
    table.rows[3].cells[1].merge(table.rows[3].cells[2])

    widths = [20, 80, 60]
    expected_dxa = [round(w * 56.6929) for w in widths]
    mod.set_table_col_widths(table, widths)

    assert table.autofit is False
    tblPr = table._tbl.tblPr
    tblLayout = tblPr.find(qn("w:tblLayout"))
    assert tblLayout is not None and tblLayout.get(qn("w:type")) == "fixed"
    tblW = tblPr.find(qn("w:tblW"))
    assert tblW is not None and int(tblW.get(qn("w:w"))) == sum(expected_dxa)

    grid_cols = table._tbl.find(qn("w:tblGrid")).findall(qn("w:gridCol"))
    assert [int(gc.get(qn("w:w"))) for gc in grid_cols] == expected_dxa

    # Строка 0 (обычная): каждая ячейка равна своей колонке
    row0_tcs = table.rows[0]._tr.findall(qn("w:tc"))
    assert [int(tc.tcPr.find(qn("w:tcW")).get(qn("w:w"))) for tc in row0_tcs] == expected_dxa

    # Строка 2 (gridSpan=3): ширина объединения равна сумме всех 3 колонок
    row2_tcs = table.rows[2]._tr.findall(qn("w:tc"))
    assert len(row2_tcs) == 1
    assert int(row2_tcs[0].tcPr.find(qn("w:gridSpan")).get(qn("w:val"))) == 3
    assert int(row2_tcs[0].tcPr.find(qn("w:tcW")).get(qn("w:w"))) == sum(expected_dxa)

    # Строка 3 (col0 + merged col1..2): [dxa0, dxa1 + dxa2]
    row3_tcs = table.rows[3]._tr.findall(qn("w:tc"))
    assert len(row3_tcs) == 2
    assert int(row3_tcs[0].tcPr.find(qn("w:tcW")).get(qn("w:w"))) == expected_dxa[0]
    assert int(row3_tcs[1].tcPr.find(qn("w:gridSpan")).get(qn("w:val"))) == 2
    assert int(row3_tcs[1].tcPr.find(qn("w:tcW")).get(qn("w:w"))) == expected_dxa[1] + expected_dxa[2]


@pytest.mark.parametrize("rel_path", MODULE_PATHS)
def test_set_table_col_widths_validates_inputs(rel_path):
    """Невалидные ширины или несоответствие числа колонок вызывают ValueError."""
    mod = _load_module("docx_mod_val", rel_path)
    doc = docx.Document()
    table = doc.add_table(rows=2, cols=3)

    with pytest.raises(ValueError):
        mod.set_table_col_widths(table, [])
    with pytest.raises(ValueError):
        mod.set_table_col_widths(table, [20, 0, 60])
    with pytest.raises(ValueError):
        mod.set_table_col_widths(table, [20, -5, 60])
    with pytest.raises(ValueError):
        mod.set_table_col_widths(table, [20, True, 60])
    with pytest.raises(ValueError):
        mod.set_table_col_widths(table, [20, 80])  # 2 ширины для 3-колоночной таблицы


@pytest.mark.parametrize("rel_path", MODULE_PATHS)
def test_check_pdf_page_breaks_skipped_when_no_converter(rel_path, tmp_path):
    mod = _load_module("docx_mod_skip", rel_path)
    sample = tmp_path / "sample.docx"
    docx.Document().save(sample)

    with patch.dict("sys.modules", {"win32com": None, "win32com.client": None}), patch(
        "shutil.which", return_value=None
    ):
        res = mod.check_pdf_page_breaks(sample, out_pdf_dir=tmp_path / "pdf")

    assert res["status"] == "skipped"
    assert res["converter"] is None
    assert res["pages"] == []
    assert res["error"]


@pytest.mark.parametrize("rel_path", MODULE_PATHS)
def test_check_pdf_page_breaks_does_not_read_stale_pdf_on_export_failure(rel_path, tmp_path):
    """Критичный сценарий: при провале экспорта старый PDF в out_pdf_dir НЕ читается."""
    mod = _load_module("docx_mod_stale", rel_path)
    sample = tmp_path / "sample.docx"
    docx.Document().save(sample)

    pdf_dir = tmp_path / "pdf"
    pdf_dir.mkdir()
    stale_pdf = pdf_dir / "sample.pdf"
    stale_pdf.write_bytes(b"%PDF-1.4 STALE OLD CONTENT")

    failed_proc = MagicMock(returncode=1, stdout="", stderr="LibreOffice conversion crash")
    with patch.dict("sys.modules", {"win32com": None, "win32com.client": None}), patch(
        "shutil.which", return_value="/usr/bin/soffice"
    ), patch("subprocess.run", return_value=failed_proc):
        res = mod.check_pdf_page_breaks(sample, out_pdf_dir=pdf_dir)

    assert res["status"] == "export_failed"
    assert res["pages"] == []
    assert res["pdf_path"] is None
    assert "rc=1" in res["error"]


@pytest.mark.parametrize("rel_path", MODULE_PATHS)
def test_check_pdf_page_breaks_handles_libreoffice_timeout(rel_path, tmp_path):
    """TimeoutExpired у LibreOffice перехватывается и возвращает export_failed."""
    mod = _load_module("docx_mod_timeout", rel_path)
    sample = tmp_path / "sample.docx"
    docx.Document().save(sample)

    with patch.dict("sys.modules", {"win32com": None, "win32com.client": None}), patch(
        "shutil.which", return_value="/usr/bin/soffice"
    ), patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="soffice", timeout=5)):
        res = mod.check_pdf_page_breaks(sample, out_pdf_dir=tmp_path / "pdf", timeout=5)

    assert res["status"] == "export_failed"
    assert "timeout" in res["error"].lower()


@pytest.mark.parametrize("rel_path", MODULE_PATHS)
def test_check_pdf_page_breaks_handles_corrupted_pdf_parse_failed(rel_path, tmp_path):
    """Повреждённый временный PDF возвращает parse_failed ДО публикации и не портит прежний final_pdf."""
    pytest.importorskip("pypdf")
    mod = _load_module("docx_mod_corrupt", rel_path)
    sample = tmp_path / "sample.docx"
    docx.Document().save(sample)

    pdf_dir = tmp_path / "pdf"
    pdf_dir.mkdir()
    existing_pdf = pdf_dir / "sample.pdf"
    existing_pdf.write_bytes(b"%PDF-1.4 PREVIOUS GOOD PDF")

    def _fake_soffice(cmd, **_kwargs):
        outdir = Path(cmd[cmd.index("--outdir") + 1])
        (outdir / "sample.pdf").write_bytes(b"NOT A VALID PDF FILE")
        return MagicMock(returncode=0, stdout="", stderr="")

    with patch.dict("sys.modules", {"win32com": None, "win32com.client": None}), patch(
        "shutil.which", return_value="/usr/bin/soffice"
    ), patch("subprocess.run", side_effect=_fake_soffice):
        res = mod.check_pdf_page_breaks(sample, out_pdf_dir=pdf_dir)

    assert res["status"] == "parse_failed"
    assert res["converter"] == "libreoffice"
    assert res["pdf_path"] is None
    assert res["error"]
    # Прежний PDF в out_pdf_dir не был перезаписан битым файлом
    assert existing_pdf.read_bytes() == b"%PDF-1.4 PREVIOUS GOOD PDF"


@pytest.mark.parametrize("rel_path", MODULE_PATHS)
def test_check_pdf_page_breaks_handles_save_oserror(rel_path, tmp_path):
    """OSError при сохранении PDF (напр., открыт в просмотрщике) возвращает save_failed с разобранными pages."""
    pytest.importorskip("pypdf")
    mod = _load_module("docx_mod_save_err", rel_path)
    sample = tmp_path / "sample.docx"
    docx.Document().save(sample)

    def _fake_soffice(cmd, **_kwargs):
        outdir = Path(cmd[cmd.index("--outdir") + 1])
        (outdir / "sample.pdf").write_bytes(b"%PDF-1.4 fake bytes")
        return MagicMock(returncode=0, stdout="", stderr="")

    p1 = MagicMock()
    p1.extract_text.return_value = "Страница 1 текста"
    fake_reader = MagicMock(pages=[p1])

    with patch.dict("sys.modules", {"win32com": None, "win32com.client": None}), patch(
        "shutil.which", return_value="/usr/bin/soffice"
    ), patch("subprocess.run", side_effect=_fake_soffice), patch(
        "pypdf.PdfReader", return_value=fake_reader
    ), patch("shutil.copy2", side_effect=PermissionError("PDF locked by Acrobat")):
        res = mod.check_pdf_page_breaks(sample, out_pdf_dir=tmp_path / "pdf")

    assert res["status"] == "save_failed"
    assert res["converter"] == "libreoffice"
    assert res["pdf_path"] is None
    assert len(res["pages"]) == 1
    assert "PDF locked by Acrobat" in res["error"]


@pytest.mark.parametrize("rel_path", MODULE_PATHS)
def test_check_pdf_page_breaks_isolates_converters_and_bounds_word_timeout(rel_path, tmp_path):
    """Word COM и LibreOffice используют разные подкаталоги; timeout Word COM перехватывается с fallback на LibreOffice."""
    pytest.importorskip("pypdf")
    mod = _load_module("docx_mod_iso", rel_path)
    sample = tmp_path / "sample.docx"
    docx.Document().save(sample)

    seen_dirs = {}
    analyzed_paths = []

    def _fake_run(cmd, **kwargs):
        if "-c" in cmd:
            # Вызов Word COM в отдельном процессе
            word_pdf = Path(cmd[-1])
            seen_dirs["word"] = word_pdf.parent
            # Даже если Word успел создать битый файл и завис по таймауту
            word_pdf.write_bytes(b"CORRUPT PARTIAL WORD OUTPUT")
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout", 5))
        # Вызов LibreOffice
        lo_dir = Path(cmd[cmd.index("--outdir") + 1])
        seen_dirs["libreoffice"] = lo_dir
        (lo_dir / "sample.pdf").write_bytes(b"%PDF-1.4 fresh libreoffice pdf")
        return MagicMock(returncode=0, stdout="", stderr="")

    p1 = MagicMock()
    p1.extract_text.return_value = "Чистая страница от LibreOffice"
    fake_reader = MagicMock(pages=[p1])

    def _spy_reader(path_str):
        analyzed_paths.append(Path(path_str))
        return fake_reader

    fake_win32 = MagicMock()
    with patch.dict("sys.modules", {"win32com": fake_win32, "win32com.client": fake_win32}), patch(
        "shutil.which", return_value="/usr/bin/soffice"
    ), patch("subprocess.run", side_effect=_fake_run), patch(
        "pypdf.PdfReader", side_effect=_spy_reader
    ):
        out_dir = tmp_path / "published_pdf"
        res = mod.check_pdf_page_breaks(sample, out_pdf_dir=out_dir, timeout=5)

    assert res["status"] == "ok"
    assert res["converter"] == "libreoffice"
    # Конвертеры использовали строго разные временные подкаталоги
    assert seen_dirs["word"] != seen_dirs["libreoffice"]
    # Разбирался именно временный PDF LibreOffice, а не конечный published_pdf/sample.pdf
    assert len(analyzed_paths) == 1
    assert analyzed_paths[0].parent == seen_dirs["libreoffice"]
    assert analyzed_paths[0].parent != out_dir
    assert Path(res["pdf_path"]).is_file()


@pytest.mark.parametrize("rel_path", MODULE_PATHS)
def test_check_pdf_page_breaks_ok_and_low_text_last_page_warning(rel_path, tmp_path):
    """Успешный свежий экспорт возвращает status='ok' и предупреждает о короткой последней странице."""
    pytest.importorskip("pypdf")
    mod = _load_module("docx_mod_ok", rel_path)
    sample = tmp_path / "sample.docx"
    docx.Document().save(sample)

    def _fake_soffice(cmd, **_kwargs):
        outdir = Path(cmd[cmd.index("--outdir") + 1])
        (outdir / "sample.pdf").write_bytes(b"%PDF-1.4 fake bytes")
        return MagicMock(returncode=0, stdout="", stderr="")

    p1 = MagicMock()
    p1.extract_text.return_value = "Основной текст первой страницы " * 15
    p2 = MagicMock()
    p2.extract_text.return_value = "Подпись: Донсков С.А."
    fake_reader = MagicMock(pages=[p1, p2])

    with patch.dict("sys.modules", {"win32com": None, "win32com.client": None}), patch(
        "shutil.which", return_value="/usr/bin/soffice"
    ), patch("subprocess.run", side_effect=_fake_soffice), patch(
        "pypdf.PdfReader", return_value=fake_reader
    ):
        res = mod.check_pdf_page_breaks(sample, out_pdf_dir=tmp_path / "pdf", orphan_chars=150)

    assert res["status"] == "ok"
    assert res["converter"] == "libreoffice"
    assert len(res["pages"]) == 2
    assert len(res["warnings"]) == 1
    assert Path(res["pdf_path"]).is_file()
