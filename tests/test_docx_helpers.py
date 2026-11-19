#!/usr/bin/env python3
"""Тесты новых табличных хелперов и PDF page-break контроля в docx_orchestrator и hush-docx."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

docx = pytest.importorskip("docx")
from docx.oxml.ns import qn  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_module(name: str, rel_path: str):
    path = REPO_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize(
    "rel_path",
    [
        "pipeline/templates/docx_orchestrator.py",
        ".agents/skills/hush-docx/scripts/helpers.py",
    ],
)
def test_table_layout_helpers_ooxml(rel_path):
    mod = _load_module("docx_mod", rel_path)
    doc = docx.Document()
    table = doc.add_table(rows=3, cols=3)

    # Строка-заголовок и запрет разрыва (идемпотентность при повторном вызове)
    mod.set_row_header(table.rows[0])
    mod.set_row_header(table.rows[0])
    mod.set_row_cant_split(table.rows[1])
    mod.set_row_cant_split(table.rows[1])

    trPr0 = table.rows[0]._tr.trPr
    assert len(trPr0.findall(qn("w:tblHeader"))) == 1
    trPr1 = table.rows[1]._tr.trPr
    assert len(trPr1.findall(qn("w:cantSplit"))) == 1

    # Объединённая строка (gridSpan=3) не должна ломаться при set_table_col_widths
    table.rows[2].cells[0].merge(table.rows[2].cells[2])
    mod.set_table_col_widths(table, [20, 80, 60])

    assert table.autofit is False
    tblLayout = table._tbl.tblPr.find(qn("w:tblLayout"))
    assert tblLayout is not None and tblLayout.get(qn("w:type")) == "fixed"

    grid_cols = table._tbl.find(qn("w:tblGrid")).findall(qn("w:gridCol"))
    assert len(grid_cols) == 3
    assert [int(gc.get(qn("w:w"))) for gc in grid_cols] == [
        round(20 * 56.6929),
        round(80 * 56.6929),
        round(60 * 56.6929),
    ]

    # Обычные ячейки получили dxa-ширины, а объединённая (gridSpan=3) осталась с gridSpan=3
    tcW0 = table.rows[0].cells[0]._tc.tcPr.find(qn("w:tcW"))
    assert tcW0.get(qn("w:type")) == "dxa"
    assert int(tcW0.get(qn("w:w"))) == round(20 * 56.6929)
    merged_span = table.rows[2].cells[0]._tc.tcPr.find(qn("w:gridSpan"))
    assert merged_span is not None and int(merged_span.get(qn("w:val"))) == 3


@pytest.mark.parametrize(
    "rel_path",
    [
        "pipeline/templates/docx_orchestrator.py",
        ".agents/skills/hush-docx/scripts/helpers.py",
    ],
)
def test_check_pdf_page_breaks_graceful_skip(rel_path, tmp_path):
    mod = _load_module("docx_mod_pdf", rel_path)
    sample = tmp_path / "sample.docx"
    docx.Document().save(sample)

    # При отсутствии Word COM и LibreOffice функция должна вернуть None (SKIP), не падая
    with patch.dict("sys.modules", {"win32com": None, "win32com.client": None}), patch(
        "shutil.which", return_value=None
    ):
        res = mod.check_pdf_page_breaks(sample, out_pdf_dir=tmp_path / "pdf")
    assert res is None
