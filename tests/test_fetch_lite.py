#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Оффлайн-тесты для pipeline/lite/fetch_lite.py (без реальных сетевых запросов)."""

import io
import urllib.error
from unittest.mock import patch, MagicMock

from pipeline.lite.fetch_lite import (
    parse_html,
    fetch_one,
    save_lite_artifact,
    batch_fetch,
)
from pipeline.verdicts import RETRIEVED_OK, BLOCKED, FAILED


SAMPLE_JOURNAL_HTML = """<!doctype html>
<html>
<head>
  <title>Статья о морфологии | Журнал</title>
  <meta name="citation_title" content="Морфологические изменения тканей пародонта">
  <meta name="citation_author" content="С. А. Донсков">
  <meta name="citation_journal_title" content="Фармакокинетика и фармакодинамика">
  <meta name="citation_date" content="2023/11/03">
  <meta name="citation_issue" content="3">
  <meta name="citation_firstpage" content="28">
  <meta name="citation_lastpage" content="38">
  <meta name="robots" content="index,follow">
</head>
<body>
  <script>var secret = 123;</script>
  <style>.a { color: red; }</style>
  <h1>Морфологические изменения тканей пародонта</h1>
  <p>Экспериментальное исследование проведено в Тверском ГМУ.</p>
</body>
</html>
"""


def _mock_response(body_bytes: bytes, url: str = "https://example.org/article/1", content_type: str = "text/html; charset=utf-8"):
    resp = MagicMock()
    resp.read.return_value = body_bytes
    resp.geturl.return_value = url
    resp.headers = {"Content-Type": content_type}
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


def test_parse_html_extracts_academic_meta_and_strips_scripts():
    res = parse_html(SAMPLE_JOURNAL_HTML)
    assert res["title"] == "Статья о морфологии | Журнал"
    assert res["h1"] == "Морфологические изменения тканей пародонта"
    meta_dict = dict(res["meta"])
    assert meta_dict["citation_title"] == "Морфологические изменения тканей пародонта"
    assert meta_dict["citation_author"] == "С. А. Донсков"
    assert meta_dict["citation_journal_title"] == "Фармакокинетика и фармакодинамика"
    assert "robots" not in meta_dict
    assert "Экспериментальное исследование" in res["text"]
    assert "secret = 123" not in res["text"]
    assert "color: red" not in res["text"]


def test_fetch_one_ok_html():
    fake = _mock_response(SAMPLE_JOURNAL_HTML.encode("utf-8"), url="https://journal.ru/view/379")
    with patch("pipeline.lite.fetch_lite.urllib.request.urlopen", return_value=fake):
        res = fetch_one("https://doi.org/10.37489/example")
    assert res["state"] == RETRIEVED_OK
    assert res["http_status"] == 200
    assert res["final_url"] == "https://journal.ru/view/379"
    assert any(k == "citation_author" and "Донсков" in v for k, v in res["meta"])


def test_fetch_one_cloudflare_page_marked_blocked():
    cf_html = "<html><head><title>Just a moment...</title></head><body>Cloudflare security verification</body></html>"
    fake = _mock_response(cf_html.encode("utf-8"))
    with patch("pipeline.lite.fetch_lite.urllib.request.urlopen", return_value=fake):
        res = fetch_one("https://blocked.example/paper")
    assert res["state"] == BLOCKED


def test_fetch_one_http_403_marked_blocked():
    err = urllib.error.HTTPError(
        url="https://mdpi.example/article",
        code=403,
        msg="Forbidden",
        hdrs={},
        fp=io.BytesIO(b"Access denied"),
    )
    with patch("pipeline.lite.fetch_lite.urllib.request.urlopen", side_effect=err):
        res = fetch_one("https://mdpi.example/article")
    assert res["state"] == BLOCKED
    assert res["http_status"] == 403
    assert "HTTP 403" in res["error"]


def test_fetch_one_network_error_marked_failed():
    with patch("pipeline.lite.fetch_lite.urllib.request.urlopen", side_effect=urllib.error.URLError("DNS fail")):
        res = fetch_one("https://unreachable.invalid/")
    assert res["state"] == FAILED
    assert "NETWORK:" in res["error"]


def test_batch_fetch_and_artifact_format(tmp_path):
    fake = _mock_response(SAMPLE_JOURNAL_HTML.encode("utf-8"), url="https://journal.ru/view/379")
    targets = [
        {"id": "ref01", "url": "https://doi.org/10.37489/example", "fact": "Донсков С.А. Статья", "expect": "2023"},
    ]
    with patch("pipeline.lite.fetch_lite.urllib.request.urlopen", return_value=fake):
        results = batch_fetch(targets, prefix="lite", timeout=10, out_dir=tmp_path)

    assert results["ref01"]["state"] == RETRIEVED_OK
    art = tmp_path / "lite_ref01.txt"
    assert art.is_file()
    content = art.read_text(encoding="utf-8")
    assert "STATE: RETRIEVED_OK" in content
    assert "SUCCESS: True" in content
    assert "FINAL_URL: https://journal.ru/view/379" in content
    assert "meta[citation_title]: Морфологические изменения тканей пародонта" in content
    assert "--- TEXT ---" in content


def test_save_lite_artifact_truncates_failed_body(tmp_path):
    res = {
        "url": "https://x.test", "final_url": "https://x.test", "content_type": "text/html",
        "http_status": 403, "state": BLOCKED, "error": "HTTP 403",
        "title": "", "h1": "", "meta": [], "text": "A" * 5000, "extractor": "http-error",
    }
    p = save_lite_artifact(tmp_path / "lite_blk.txt", res)
    txt = p.read_text(encoding="utf-8")
    assert "STATE: BLOCKED" in txt
    assert "A" * 1500 in txt
    assert "A" * 2000 not in txt


def test_parse_html_stdlib_fallback_without_bs4():
    """CI запускается без [lite]: fallback-парсер stdlib должен извлекать те же поля."""
    with patch.dict("sys.modules", {"bs4": None}):
        res = parse_html(SAMPLE_JOURNAL_HTML)
    assert res["extractor"] == "stdlib-html"
    assert res["title"] == "Статья о морфологии | Журнал"
    assert res["h1"] == "Морфологические изменения тканей пародонта"
    meta_dict = dict(res["meta"])
    assert meta_dict["citation_title"] == "Морфологические изменения тканей пародонта"
    assert meta_dict["citation_author"] == "С. А. Донсков"
    assert "robots" not in meta_dict
    assert "Экспериментальное исследование" in res["text"]
    assert "secret = 123" not in res["text"]
