"""Тесты быстрого режима (pipeline/manual/factcheck_manual.py).

Unit-часть: HTML-экстрактор, значимые термины, маппинг файлов на цели,
извлечение текста, анализ источника (DOI / coverage / BLOCKED).
Интеграционная часть: subprocess-прогоны как в test_sam_smoke.py —
коды выхода 0/1/2, артефакты man_{id}.txt, orphan-предупреждения.
Сеть не используется.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from pipeline.manual.factcheck_manual import (
    analyze_source,
    html_to_text,
    load_source_text,
    match_files,
    significant_terms,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCANNER = REPO_ROOT / "pipeline" / "manual" / "factcheck_manual.py"
_ENV = {**os.environ, "PYTHONUTF8": "1"}

TARGET = {"id": "ref01", "url": "https://doi.org/10.1038/s41591-018-0300-7",
          "fact": "Topol E.J. High-performance medicine: the convergence of human and artificial intelligence",
          "expect": "DOI 10.1038/s41591-018-0300-7"}


def run_scanner(*args, timeout=120):
    return subprocess.run(
        [sys.executable, str(SCANNER), *map(str, args)],
        cwd=str(REPO_ROOT), env=_ENV, capture_output=True, timeout=timeout,
    )


# =================== unit: HTML-экстрактор ===================

def test_html_to_text_strips_script_and_style():
    raw = ("<html><head><title>t</title><style>b{color:red}</style></head>"
           "<body><script>var x=1;</script><p>Hello world content</p></body></html>")
    text = html_to_text(raw)
    assert "Hello world content" in text
    assert "var x=1" not in text
    assert "color:red" not in text
    assert "t" not in text.split()  # <title> скрыт


def test_html_to_text_malformed_still_extracts():
    # HTMLParser прощает незакрытые теги — текст извлекается без исключений
    raw = "<p>unclosed <b>tags everywhere"
    text = html_to_text(raw)
    assert "unclosed tags everywhere" in text


def test_html_to_text_decodes_entities():
    assert "AT&T" in html_to_text("<p>AT&amp;T rule</p>")


# =================== unit: значимые термины ===================

def test_significant_terms_filters_stopwords_and_short():
    terms = significant_terms("The convergence of human and AI in medicine")
    assert "convergence" in terms and "human" in terms and "medicine" in terms
    assert "the" not in terms and "of" not in terms and "and" not in terms


def test_significant_terms_empty_and_none():
    assert significant_terms("", None) == []


# =================== unit: маппинг файлов ===================

def _mk_files(tmp_path, names):
    for n in names:
        (tmp_path / n).write_text("x", encoding="utf-8")


def test_match_files_basic_and_orphans(tmp_path):
    _mk_files(tmp_path, ["ref01_a.txt", "ref01.b.txt", "ref01.txt", "junk.txt"])
    targets = [{"id": "ref01"}, {"id": "ref02"}]
    mapping, orphans = match_files(targets, tmp_path)
    names = {p.name for p in mapping["ref01"]}
    assert names == {"ref01_a.txt", "ref01.b.txt", "ref01.txt"}
    assert mapping["ref02"] == []
    assert [p.name for p in orphans] == ["junk.txt"]


def test_match_files_long_ids_first(tmp_path):
    # ref1 не должен съесть ref10_*.txt
    _mk_files(tmp_path, ["ref1_x.txt", "ref10_y.txt"])
    targets = [{"id": "ref1"}, {"id": "ref10"}]
    mapping, orphans = match_files(targets, tmp_path)
    assert [p.name for p in mapping["ref1"]] == ["ref1_x.txt"]
    assert [p.name for p in mapping["ref10"]] == ["ref10_y.txt"]
    assert orphans == []


def test_match_files_missing_dir(tmp_path):
    mapping, orphans = match_files([{"id": "ref01"}], tmp_path / "nope")
    assert mapping == {"ref01": []} and orphans == []


# =================== unit: извлечение текста ===================

def test_load_txt_and_empty(tmp_path):
    p = tmp_path / "a.txt"
    p.write_text("some text here", encoding="utf-8")
    text, tag = load_source_text(p)
    assert tag == "txt" and "some text" in text

    empty = tmp_path / "b.txt"
    empty.write_text("   \n  ", encoding="utf-8")
    text, tag = load_source_text(empty)
    assert text is None and tag == "empty"


def test_load_unsupported_ext(tmp_path):
    p = tmp_path / "a.docx"
    p.write_bytes(b"PK\x03\x04")
    text, tag = load_source_text(p)
    assert text is None and tag == "unsupported"


def test_load_pdf_without_pypdf(tmp_path):
    p = tmp_path / "a.pdf"
    p.write_bytes(b"%PDF-1.4 broken")
    text, tag = load_source_text(p)
    # pypdf не установлен -> pypdf-not-installed; установлен -> unreadable (битый pdf)
    assert tag in ("pypdf-not-installed", "unreadable") and text is None


# =================== unit: analyze_source ===================

def test_analyze_doi_match_and_coverage(tmp_path):
    p = tmp_path / "ref01_src.txt"
    p.write_text("High-performance medicine: the convergence of human and "
                 "artificial intelligence. Eric Topol. DOI: 10.1038/s41591-018-0300-7.",
                 encoding="utf-8")
    rec = analyze_source(TARGET, p, window=300)
    assert rec["state"] == "RETRIEVED_OK"
    assert rec["doi"] == "MATCH"
    assert rec["coverage"] == "8/8 (100%)"
    assert "medicine" in rec["quote"].lower()
    assert rec["quote_terms"] == "8/8"


def test_analyze_doi_mismatch(tmp_path):
    p = tmp_path / "ref01_x.txt"
    p.write_text("Completely unrelated content with DOI 10.1234/other.doi inside", encoding="utf-8")
    rec = analyze_source(TARGET, p, window=300)
    assert rec["doi"].startswith("MISMATCH")
    assert "10.1234/other" in rec["doi"]


def test_analyze_doi_not_found_but_text_ok(tmp_path):
    p = tmp_path / "ref01_y.txt"
    p.write_text("medicine convergence text without any digital identifier", encoding="utf-8")
    rec = analyze_source(TARGET, p, window=300)
    assert rec["doi"] == "not-found"
    assert rec["state"] == "RETRIEVED_OK"


def test_analyze_blocked_page(tmp_path):
    p = tmp_path / "ref01_cf.html"
    p.write_text("<html><body><p>Checking your browser. cloudflare security verification</p></body></html>",
                 encoding="utf-8")
    rec = analyze_source(TARGET, p, window=300)
    assert rec["state"] == "BLOCKED"


def test_analyze_target_without_doi(tmp_path):
    p = tmp_path / "ref02_z.txt"
    p.write_text("plain evidence text", encoding="utf-8")
    target = {"id": "ref02", "url": "https://example.org/x", "fact": "plain evidence text"}
    rec = analyze_source(target, p, window=300)
    assert "doi" not in rec
    assert rec["state"] == "RETRIEVED_OK"


# =================== интеграция: subprocess ===================

def test_help_exit_zero():
    assert run_scanner("--help").returncode == 0


def test_missing_targets_exit_two():
    assert run_scanner("--prefix", "man").returncode == 2


def test_invalid_targets_json_exit_two(tmp_path):
    p = tmp_path / "targets.json"
    p.write_text("{ broken", encoding="utf-8")
    assert run_scanner("--targets", p).returncode == 2


def _setup(tmp_path, files):
    tdir = tmp_path / "manual"
    tdir.mkdir()
    for name, content in files.items():
        (tdir / name).write_text(content, encoding="utf-8")
    targets = tmp_path / "targets.json"
    targets.write_text(json.dumps([TARGET]), encoding="utf-8")
    return targets, tdir


def test_happy_path_exit_zero(tmp_path):
    targets, tdir = _setup(tmp_path, {
        "ref01_topol.txt": "High-performance medicine: the convergence of human "
                           "and artificial intelligence. Eric Topol. "
                           "DOI: 10.1038/s41591-018-0300-7.",
    })
    out = tmp_path / "out"
    r = run_scanner("--targets", targets, "--sources-dir", tdir, "--out-dir", out)
    assert r.returncode == 0
    assert "EVID" in r.stdout.decode("utf-8", "replace")
    report = out / "man_ref01.txt"
    assert report.is_file()
    body = report.read_text(encoding="utf-8")
    assert "STATE: RETRIEVED_OK" in body
    assert "DOI: MATCH" in body
    assert "SUCCESS: True" in body
    assert "НЕ вердикт" in body


def test_blocked_only_exit_one(tmp_path):
    targets, tdir = _setup(tmp_path, {
        "ref01_cf.html": "<html><body>Access denied: cloudflare</body></html>",
    })
    out = tmp_path / "out"
    r = run_scanner("--targets", targets, "--sources-dir", tdir, "--out-dir", out)
    assert r.returncode == 1
    assert "BLKD" in r.stdout.decode("utf-8", "replace")
    assert "STATE: BLOCKED" in (out / "man_ref01.txt").read_text(encoding="utf-8")


def test_no_sources_exit_one(tmp_path):
    targets, _ = _setup(tmp_path, {})
    out = tmp_path / "out"
    r = run_scanner("--targets", targets, "--sources-dir", tmp_path / "manual", "--out-dir", out)
    assert r.returncode == 1
    assert "NO FILES" in r.stdout.decode("utf-8", "replace")


def test_orphan_warning(tmp_path):
    targets, tdir = _setup(tmp_path, {
        "ref01_ok.txt": "medicine convergence DOI 10.1038/s41591-018-0300-7 content",
        "stray.txt": "orphan",
    })
    r = run_scanner("--targets", targets, "--sources-dir", tdir, "--out-dir", tmp_path / "out")
    out_text = r.stdout.decode("utf-8", "replace")
    assert "orphan" in out_text and "stray.txt" in out_text
