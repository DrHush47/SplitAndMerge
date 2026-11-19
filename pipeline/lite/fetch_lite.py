#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_lite.py — лёгкий HTTP/meta/PDF-фетчер для профиля `lite` (без браузеров).

Закрывает промежуток между Ур.0.5 (OpenAlex) / Ур.0.7 (BioMed) и тяжёлыми браузерными
краулерами Ур.2–3 (Crawl4AI / Scrapling): за доли секунды скачивает открытые страницы
российских журналов, сайтов вузов и PDF-файлы, извлекая академические метатеги
(`citation_*`, `DC.*`, `og:title`), заголовки и чистый текст.

Зависимости:
  - Сеть: стандартная библиотека Python (`urllib.request`, `ssl`)
  - HTML-разбор: `beautifulsoup4` (из профиля `lite`; при отсутствии — stdlib fallback)
  - PDF-разбор: `pypdf` (из профиля `lite`; при отсутствии — мягкий пропуск PDF)

Примеры запуска:
    .venv/Scripts/python.exe pipeline/lite/fetch_lite.py --targets pipeline/targets.json --prefix lite --timeout 15
    .venv/Scripts/python.exe pipeline/lite/fetch_lite.py --url "https://doi.org/10.37489/2587-7836-2023-3-28-38"
"""

import argparse
import io
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from pipeline.common import read_targets, validate_prefix, fix_windows_console, default_out_dir
from pipeline.verdicts import classify_retrieval, detect_blocked, RETRIEVED_OK, BLOCKED, FAILED

MAX_TEXT_CHARS = 100_000
TRUNCATE_KEEP_CHARS = 1_500
DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

ACADEMIC_META_KEYS = (
    "citation_title",
    "citation_journal_title",
    "citation_author",
    "citation_author_institution",
    "citation_date",
    "citation_publication_date",
    "citation_volume",
    "citation_issue",
    "citation_firstpage",
    "citation_lastpage",
    "citation_doi",
    "citation_pdf_url",
    "dc.title",
    "dc.title.alternative",
    "dc.creator",
    "dc.date",
    "og:title",
)

# HTTP-коды, указывающие на anti-bot / запрет доступа (→ BLOCKED, эскалация в Ур.5 или [web])
BLOCK_HTTP_CODES = {401, 403, 429, 451}


# ---------------------------------------------------------------------------
# HTML / PDF извлечение (BeautifulSoup + stdlib fallback + pypdf)
# ---------------------------------------------------------------------------

class _FallbackHTMLParser(HTMLParser):
    """Минимальный stdlib-парсер HTML на случай запуска без beautifulsoup4."""

    def __init__(self):
        super().__init__()
        self.meta = []
        self.title = ""
        self.h1 = ""
        self._in_title = False
        self._in_h1 = False
        self._skip_depth = 0
        self._chunks = []

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        if t in ("script", "style", "noscript"):
            self._skip_depth += 1
        elif t == "title":
            self._in_title = True
        elif t == "h1" and not self.h1:
            self._in_h1 = True
        elif t == "meta":
            name = (attr_map.get("name") or attr_map.get("property") or "").strip()
            content = attr_map.get("content", "").strip()
            if name and content:
                self.meta.append((name, content))

    def handle_endtag(self, tag):
        t = tag.lower()
        if t in ("script", "style", "noscript") and self._skip_depth > 0:
            self._skip_depth -= 1
        elif t == "title":
            self._in_title = False
        elif t == "h1":
            self._in_h1 = False

    def handle_data(self, data):
        if self._skip_depth > 0:
            return
        if self._in_title:
            self.title += data
        if self._in_h1:
            self.h1 += data
        s = data.strip()
        if s:
            self._chunks.append(s)


def _decode_bytes(raw: bytes, content_type: str = "") -> str:
    """Декодировать HTML-байты с учётом charset из Content-Type и частых RU-кодировок."""
    m = re.search(r"charset=([^\s;\"']+)", content_type or "", re.IGNORECASE)
    encodings = []
    if m:
        encodings.append(m.group(1).strip())
    encodings.extend(["utf-8", "cp1251", "latin-1"])
    for enc in encodings:
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_html(html: str) -> dict:
    """Извлечь title, h1, академические метатеги и чистый текст из HTML."""
    meta_out = []
    title = ""
    h1 = ""
    text = ""
    extractor = "stdlib-html"

    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        extractor = "beautifulsoup4"

        if soup.title:
            title = re.sub(r"\s+", " ", soup.title.get_text(" ", strip=True))
        h1_tag = soup.find("h1")
        if h1_tag:
            h1 = re.sub(r"\s+", " ", h1_tag.get_text(" ", strip=True))

        for m in soup.find_all("meta"):
            name = (m.get("name") or m.get("property") or "").strip()
            content = (m.get("content") or "").strip()
            if name and content and name.lower() in ACADEMIC_META_KEYS:
                meta_out.append((name, re.sub(r"\s+", " ", content)))

        for bad in soup(["script", "style", "noscript"]):
            bad.decompose()
        raw_text = soup.get_text("\n", strip=True)
        lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in raw_text.splitlines()]
        text = "\n".join(ln for ln in lines if ln)
    except ImportError:
        parser = _FallbackHTMLParser()
        parser.feed(html)
        title = re.sub(r"\s+", " ", parser.title).strip()
        h1 = re.sub(r"\s+", " ", parser.h1).strip()
        meta_out = [
            (k, re.sub(r"\s+", " ", v))
            for k, v in parser.meta
            if k.lower() in ACADEMIC_META_KEYS
        ]
        text = "\n".join(parser._chunks)

    return {
        "title": title,
        "h1": h1,
        "meta": meta_out,
        "text": text[:MAX_TEXT_CHARS],
        "extractor": extractor,
    }


def extract_pdf_bytes(raw: bytes) -> tuple:
    """Извлечь текст из PDF-байтов через pypdf. Возвращает (text, error, extractor)."""
    try:
        import pypdf
    except ImportError:
        return "", "pypdf-not-installed (install profile `lite`)", "pdf-skipped"
    try:
        reader = pypdf.PdfReader(io.BytesIO(raw))
        pages = [(p.extract_text() or "") for p in reader.pages]
        text = "\n\n".join(p.strip() for p in pages if p.strip())
        return text[:MAX_TEXT_CHARS], None, f"pypdf ({len(reader.pages)} pages)"
    except Exception as exc:
        return "", f"PDF extract error: {type(exc).__name__}: {exc}", "pypdf-error"


# ---------------------------------------------------------------------------
# Сетевой запрос
# ---------------------------------------------------------------------------

def fetch_one(url: str, timeout: int = 15) -> dict:
    """Выполнить лёгкий HTTP GET без браузера и классифицировать результат."""
    req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_UA})
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            final_url = resp.geturl()
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:TRUNCATE_KEEP_CHARS]
        except Exception:
            pass
        is_block = exc.code in BLOCK_HTTP_CODES or detect_blocked(body)
        state = BLOCKED if is_block else FAILED
        return {
            "url": url,
            "final_url": url,
            "content_type": "",
            "http_status": exc.code,
            "state": state,
            "error": f"HTTP {exc.code}" + (" (blocked — escalate to manual Ур.5 or [web])" if is_block else ""),
            "title": "",
            "h1": "",
            "meta": [],
            "text": body,
            "extractor": "http-error",
        }
    except urllib.error.URLError as exc:
        return {
            "url": url, "final_url": url, "content_type": "", "http_status": None,
            "state": FAILED, "error": f"NETWORK: {exc.reason}",
            "title": "", "h1": "", "meta": [], "text": "", "extractor": "network-error",
        }
    except Exception as exc:
        return {
            "url": url, "final_url": url, "content_type": "", "http_status": None,
            "state": FAILED, "error": f"{type(exc).__name__}: {exc}",
            "title": "", "h1": "", "meta": [], "text": "", "extractor": "error",
        }

    is_pdf = ("application/pdf" in content_type.lower()) or final_url.lower().split("?")[0].endswith(".pdf")
    if is_pdf:
        text, err, extractor = extract_pdf_bytes(raw)
        state = classify_retrieval(text, err)
        return {
            "url": url, "final_url": final_url, "content_type": content_type,
            "http_status": 200, "state": state, "error": err,
            "title": "", "h1": "", "meta": [], "text": text, "extractor": extractor,
        }

    html = _decode_bytes(raw, content_type)
    parsed = parse_html(html)
    # Если HTML содержит метатеги или текст — проверяем на блокировку/пустоту
    combined_check = parsed["title"] + "\n" + parsed["text"]
    state = classify_retrieval(combined_check, None)
    err = "Blocked marker detected" if state == BLOCKED else ("Empty page (possible JS-SPA)" if state == FAILED else None)
    return {
        "url": url,
        "final_url": final_url,
        "content_type": content_type,
        "http_status": 200,
        "state": state,
        "error": err,
        "title": parsed["title"],
        "h1": parsed["h1"],
        "meta": parsed["meta"],
        "text": parsed["text"],
        "extractor": parsed["extractor"],
    }


# ---------------------------------------------------------------------------
# Сохранение артефактов (совместимый формат шапки с каскадом)
# ---------------------------------------------------------------------------

def save_lite_artifact(fname: Path, res: dict, fact: str = "", expect: str = "") -> Path:
    fname.parent.mkdir(parents=True, exist_ok=True)
    ok = res["state"] == RETRIEVED_OK
    with open(fname, "w", encoding="utf-8") as f:
        f.write(f"URL: {res['url']}\n")
        if res["final_url"] and res["final_url"] != res["url"]:
            f.write(f"FINAL_URL: {res['final_url']}\n")
        if fact:
            f.write(f"FACT: {fact}\n")
        if expect:
            f.write(f"EXPECT: {expect}\n")
        f.write(f"HTTP_STATUS: {res.get('http_status')}\n")
        f.write(f"CONTENT_TYPE: {res.get('content_type', '')}\n")
        f.write(f"EXTRACTOR: {res.get('extractor', '')}\n")
        f.write(f"STATE: {res['state']}\n")
        f.write(f"SUCCESS: {ok}\n")
        if res.get("error"):
            f.write(f"ERROR: {res['error']}\n")
        f.write("\n" + "=" * 70 + "\n")
        if res.get("title") or res.get("h1") or res.get("meta"):
            f.write("--- META ---\n")
            if res.get("title"):
                f.write(f"title: {res['title']}\n")
            if res.get("h1"):
                f.write(f"h1: {res['h1']}\n")
            for k, v in res.get("meta", []):
                f.write(f"meta[{k}]: {v}\n")
            f.write("\n--- TEXT ---\n")
        body = res.get("text", "")
        f.write(body if ok else body[:TRUNCATE_KEEP_CHARS])
    return fname


def batch_fetch(targets: list, prefix: str = "lite", timeout: int = 15, out_dir=None) -> dict:
    """Пакетный прогон лёгкого фетчера по targets.json."""
    out_dir = Path(out_dir) if out_dir else default_out_dir()
    results = {}
    for i, t in enumerate(targets):
        tid = t["id"]
        url = t["url"]
        print(f"[{tid}] {url}", flush=True)
        t0 = time.time()
        res = fetch_one(url, timeout=timeout)
        elapsed = time.time() - t0
        fname = out_dir / f"{prefix}_{tid}.txt"
        save_lite_artifact(fname, res, fact=t.get("fact", ""), expect=t.get("expect", ""))
        meta_cnt = len(res.get("meta", []))
        print(
            f"    state={res['state']}  http={res.get('http_status')}  "
            f"meta={meta_cnt}  chars={len(res.get('text', ''))}  "
            f"elapsed={elapsed:.1f}s  saved={fname}",
            flush=True,
        )
        results[tid] = res
        if i + 1 < len(targets):
            time.sleep(0.25)

    ok_n = sum(1 for r in results.values() if r["state"] == RETRIEVED_OK)
    blk_n = sum(1 for r in results.values() if r["state"] == BLOCKED)
    fail_n = sum(1 for r in results.values() if r["state"] == FAILED)
    print("\n" + "=" * 70, flush=True)
    print(f"SUMMARY (fetch_lite): RETRIEVED_OK={ok_n}  BLOCKED={blk_n}  FAILED={fail_n}  TOTAL={len(results)}", flush=True)
    if blk_n or fail_n:
        print("HINT: для BLOCKED/FAILED — ручной трек Ур.5 (manual.md) или доустановка `[web]` с подтверждения пользователя.", flush=True)
    return results


def main():
    ap = argparse.ArgumentParser(description="Лёгкий HTTP/meta/PDF-фетчер (профиль lite, без браузеров)")
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--targets", help="путь к targets.json")
    grp.add_argument("--url", help="одиночный URL для быстрого извлечения метатегов и текста")
    ap.add_argument("--prefix", default="lite", help="префикс выходных файлов в пакетном режиме (default: lite)")
    ap.add_argument("--out-dir", default=None, help="каталог артефактов (default: <repo>/workspace)")
    ap.add_argument("--out", default=None, help="файл для сохранения в режиме --url")
    ap.add_argument("--timeout", type=int, default=15, help="таймаут запроса в секундах (default: 15)")
    args = ap.parse_args()

    fix_windows_console()

    if args.url:
        res = fetch_one(args.url, timeout=args.timeout)
        if args.out:
            out_path = save_lite_artifact(Path(args.out), res)
            print(f"STATE={res['state']}  META={len(res['meta'])}  CHARS={len(res['text'])}  SAVED={out_path}")
        else:
            print(f"URL: {res['url']} -> {res['final_url']}")
            print(f"STATE: {res['state']}  HTTP: {res['http_status']}  EXTRACTOR: {res['extractor']}")
            if res.get("error"):
                print(f"ERROR: {res['error']}")
            if res.get("title"):
                print(f"TITLE: {res['title']}")
            if res.get("h1"):
                print(f"H1: {res['h1']}")
            for k, v in res.get("meta", []):
                print(f"  meta[{k}]: {v}")
            print(f"TEXT ({len(res['text'])} chars): {res['text'][:400]}")
        sys.exit(0 if res["state"] == RETRIEVED_OK else 1)

    validate_prefix(args.prefix)
    targets = read_targets(Path(args.targets), validate_url_https=True)
    results = batch_fetch(targets, prefix=args.prefix, timeout=args.timeout, out_dir=args.out_dir)
    all_ok = all(r["state"] == RETRIEVED_OK for r in results.values())
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
