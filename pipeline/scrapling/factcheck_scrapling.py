#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
factcheck_scrapling.py (v1)
============================

Фактчек-краулер на базе Scrapling (StealthySession).
Замена FireCrawl на Ур.3 каскада факт-чекинга — бесплатно.

Использование:
    python scrapling/factcheck_scrapling.py --targets targets.json [--prefix sc] [--timeout 90]

Зависимости: scrapling[all] (StealthyFetcher, StealthySession)
Синхронный (StealthySession — sync, не async).

Особенности реализации (по результатам разведки API v0.4.11):
    - page.markdown — НЕ СУЩЕСТВУЕТ. Используем fallback: get_all_text → html_content → body.decode
    - page.text (TextHandler) — str() возвращает пустую строку. Используем get_all_text().
    - StealthySession — синхронный (with, не async with).
    - timeout — в секундах, конвертится в миллисекунды (Playwright).
    - Без threading: StealthFetchParams.timeout работает нативно.
"""

import argparse
import sys
import time
from pathlib import Path

# Shared pipeline utilities (pipeline/common.py)
sys.path.insert(0, str(Path(__file__).parent.parent))
from common import read_targets, validate_prefix, fix_windows_console

from scrapling.fetchers import StealthySession

MAX_TEXT_CHARS = 200_000
TRUNCATE_KEEP_CHARS = 1_500


# =================== ИЗВЛЕЧЕНИЕ ТЕКСТА ===================

def extract_text(page):
    """Безопасное извлечение текста из page — с fallback.
    
    Возвращает (text: str, extractor: str).
    extractor: 'text' | 'html' | 'body' | 'empty'
    
    Приоритет:
    1. page.get_all_text() — plain text (без HTML-тегов)
    2. str(page.html_content) — HTML (полный документ)
    3. page.body.decode('utf-8') — raw body (байты → строка)
    """
    # 1. get_all_text — чистый текст
    try:
        t = page.get_all_text()
        if t is not None:
            s = str(t)
            if s.strip():
                return s, 'text'
    except Exception:
        pass

    # 2. html_content — HTML
    try:
        t = page.html_content
        if t is not None:
            s = str(t)
            if s.strip() and len(s) > 100:
                return s, 'html'
    except Exception:
        pass

    # 3. body.decode — raw body
    try:
        t = page.body
        if t is not None:
            s = t.decode('utf-8', errors='replace')
            if s.strip():
                return s, 'body'
    except Exception:
        pass

    return '', 'empty'


# =================== ОСНОВНОЙ ЦИКЛ ===================

def _save_result(target, text, success, error, extractor, prefix, status_code):
    """Сохранить результат в файл."""
    fname = Path(__file__).parent / f"{prefix}_{target['id']}.txt"
    fname.parent.mkdir(parents=True, exist_ok=True)
    
    original_len = len(text)
    if original_len > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS] + f"\n\n[TRUNCATED from {original_len} chars to {MAX_TEXT_CHARS}]"
    
    with open(fname, "w", encoding="utf-8") as f:
        f.write(f"URL: {target['url']}\n")
        f.write(f"FACT: {target['fact']}\n")
        f.write(f"EXPECT: {target.get('expect', '')}\n")
        f.write(f"SUCCESS: {success}\n")
        f.write(f"EXTRACTOR: {extractor}\n")
        f.write(f"STATUS: {status_code}\n")
        if error:
            f.write(f"ERROR: {error}\n")
        f.write("\n" + "=" * 70 + "\n")
        if text:
            if error:
                f.write(text[:TRUNCATE_KEEP_CHARS] if text else "")
            else:
                f.write(text)
    return fname


def crawl_batch(targets, prefix, timeout, adaptive, css_selector, solve_cf):
    """Batch-парсинг URL через StealthySession.
    
    StealthySession держит браузер открытым между запросами — 
    это в 10-20× быстрее, чем открывать/закрывать для каждого URL.
    """
    results = {}
    
    with StealthySession(headless=True, solve_cloudflare=solve_cf) as session:
        for target in targets:
            url = target["url"]
            tid = target["id"]
            print(f"[{tid}] {url}", flush=True)
            print(f"    fact   : {target['fact']}", flush=True)
            print(f"    expect : {target.get('expect', '')}", flush=True)
            
            start_ts = time.time()
            try:
                # timeout в Scrapling/Playwright — в миллисекундах
                page = session.fetch(url, timeout=timeout * 1000, network_idle=True)
                elapsed = time.time() - start_ts
                
                status_code = getattr(page, 'status', None)
                print(f"    status : {status_code}  elapsed={elapsed:.1f}s", flush=True)
                
                # Adaptive CSS parsing или обычный
                if css_selector:
                    try:
                        if adaptive:
                            elements = page.css(css_selector, adaptive=True)
                        else:
                            elements = page.css(css_selector)
                        text = '\n'.join(str(e) for e in elements) if elements else ''
                        extractor = f'css+adaptive' if adaptive else f'css'
                        success = bool(text.strip())
                    except Exception as exc:
                        print(f"    css err: {exc}", flush=True)
                        text, extractor = extract_text(page)
                        success = bool(text.strip())
                else:
                    text, extractor = extract_text(page)
                    success = bool(text.strip())
                
                error = None
                if not success:
                    error = "EMPTY"
                
                print(f"    extract: {extractor}  len={len(text)}  success={success}", flush=True)
                
            except Exception as exc:
                elapsed = time.time() - start_ts
                exc_name = type(exc).__name__
                if 'Timeout' in exc_name or 'timeout' in str(exc).lower():
                    error = f"timeout after {elapsed:.0f}s (limit={timeout}s): {exc}"
                    extractor = "timeout"
                    print(f"    status : TIMEOUT — {error}", flush=True)
                else:
                    error = f"{exc_name}: {exc}"
                    extractor = "error"
                    print(f"    status : ERROR — {error}", flush=True)
                text = ""
                success = False
                status_code = None
            
            # Сохраняем результат
            fname = _save_result(target, text, success, error, extractor, prefix, status_code)
            print(f"    saved  : {fname}", flush=True)
            
            results[tid] = {
                "fact": target["fact"],
                "url": url,
                "text": text,
                "success": success,
                "error": error,
                "extractor": extractor,
                "status": status_code,
            }
    
    return results


# =================== MAIN ===================

def main():
    ap = argparse.ArgumentParser(description="Scrapling fact-checker (batch runner)")
    ap.add_argument("--targets", required=True, help="path to JSON with TARGETS list")
    ap.add_argument("--prefix", default="sc", help="output filename prefix (default: sc)")
    ap.add_argument("--timeout", type=int, default=90, help="per-URL fetch timeout (s) (default: 90)")
    ap.add_argument("--adaptive", action="store_true",
                    help="Use adaptive=True for re-parsing sites with changed structure")
    ap.add_argument("--css-selector", default=None,
                    help="Optional CSS selector to extract specific content (e.g. '.article-abstract')")
    ap.add_argument("--no-cloudflare", action="store_true",
                    help="Disable Cloudflare Turnstile solving (faster for simple sites)")
    args = ap.parse_args()
    
    fix_windows_console()
    
    validate_prefix(args.prefix)
    targets = read_targets(Path(args.targets))
    print(f"Loaded {len(targets)} targets from {args.targets}", flush=True)
    print(f"Settings: timeout={args.timeout}s, adaptive={args.adaptive}, "
          f"css_selector={args.css_selector}, solve_cloudflare={not args.no_cloudflare}", flush=True)
    
    results = crawl_batch(
        targets=targets,
        prefix=args.prefix,
        timeout=args.timeout,
        adaptive=args.adaptive,
        css_selector=args.css_selector,
        solve_cf=not args.no_cloudflare,
    )
    
    # Summary
    print("\n" + "=" * 70, flush=True)
    print("SUMMARY", flush=True)
    print("=" * 70, flush=True)
    ok = sum(1 for r in results.values() if r["success"])
    fail = len(results) - ok
    print(f"OK={ok}  FAIL={fail}  TOTAL={len(results)}", flush=True)
    for tid, r in results.items():
        flag = "OK  " if r["success"] else "FAIL"
        extra = ""
        if r.get("error"):
            extra += f"  err={r['error']!r}"
        if r.get("extractor"):
            extra += f"  via={r['extractor']}"
        if r.get("status"):
            extra += f"  http={r['status']}"
        print(f"  [{flag}] {tid}  {r['url']}{extra}", flush=True)


if __name__ == "__main__":
    main()
