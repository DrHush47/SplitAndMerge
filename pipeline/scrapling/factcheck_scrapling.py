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
    - ЖЁСТКИЙ ДЕДЛАЙН: внутренний цикл solve_cloudflare библиотеки таймауту
      fetch НЕ подчиняется (зафиксировано зависание на managed-Turnstile на 5+ мин
      при --timeout 90). Поэтому каждая цель — свой поток со своей сессией
      и дедлайном timeout + DEADLINE_GRACE_S; по истечении — провал с эскалацией
      (зависший поток/браузер доживает до конца процесса).
    - Одна попытка на цель, без повторных заходов: Turnstile либо берётся за первые
      2-3 цикла (~30-40 сек), либо не берётся никогда.
"""

import argparse
import concurrent.futures
import glob
import os
import sys
import threading
import time
from pathlib import Path

# Shared pipeline utilities (pipeline/common.py)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import read_targets, validate_prefix, fix_windows_console, default_out_dir

from scrapling.fetchers import StealthySession

MAX_TEXT_CHARS = 200_000
TRUNCATE_KEEP_CHARS = 1_500

# Жёсткий wall-clock дедлайн на цель = timeout + эта надбавка (сек).
# Покрывает внутренний цикл solve_cloudflare, которому fetch-timeout не указ.
DEADLINE_GRACE_S = 30


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

def _save_result(target, text, success, error, extractor, prefix, status_code, out_dir):
    """Сохранить результат в файл."""
    fname = Path(out_dir) / f"{prefix}_{target['id']}.txt"
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
            f.write(text[:TRUNCATE_KEEP_CHARS] if error else text)
    return fname


def _resolve_browser_path(cli_value=None):
    """Resolve a Chromium executable path for StealthySession.

    Priority: --browser-path CLI > SCRAPLING_EXECUTABLE_PATH env >
    Puppeteer cache autodetect (ms-playwright cache is often empty on this
    machine while the Puppeteer-cached Chrome exists and works).
    Returns None to let Scrapling/Playwright use its own default.
    """
    candidate = cli_value or os.environ.get("SCRAPLING_EXECUTABLE_PATH")
    if candidate:
        p = Path(candidate)
        if p.is_file():
            return str(p)
        print(f"    warn: browser path not found ({candidate}) — falling back to autodetect", flush=True)

    # Autodetect: newest Puppeteer-cached chrome.exe (Windows Git Bash paths)
    patterns = [
        os.path.expanduser("~/.cache/puppeteer/chrome/win64-*/chrome-win64/chrome.exe"),
        os.path.expanduser("~/.cache/puppeteer/chrome/mac_*/chrome-mac-*/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"),
        os.path.expanduser("~/.cache/puppeteer/chrome/linux-*/chrome-linux64/chrome"),
    ]
    found = []
    for pat in patterns:
        found.extend(glob.glob(pat))
    if found:
        # newest version wins (glob sorts lexically; version dirs are zero-padded enough)
        best = sorted(found)[-1]
        print(f"    browser: autodetected Puppeteer-cached Chrome: {best}", flush=True)
        return best
    return None


def _run_isolated(fn, args, deadline):
    """Запуск fn(*args) в daemon-потоке с дедлайном (сек).

    Daemon важен: зависший fetch (Cloudflare-цикл) не должен держать выход
    из процесса — pool.shutdown(wait=False) этого не гарантирует, т.к. потоки
    ThreadPoolExecutor не daemon. Осиротевший браузер зависшей цели может
    задержаться в процессах ОС — приемлемо для редкого пути.
    Бросает concurrent.futures.TimeoutError по истечении дедлайна.
    """
    fut = concurrent.futures.Future()

    def _target():
        if fut.cancelled():
            return
        try:
            fut.set_result(fn(*args))
        except Exception as exc:  # noqa: BLE001 — intentional: transport any worker error to the main thread
            if not fut.done():
                fut.set_exception(exc)

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    return fut.result(timeout=deadline)


def _open_session(exe_path, solve_cf, real_chrome):
    """Создать StealthySession (контекстом управляет вызывающий worker)."""
    session_kwargs = dict(headless=True, solve_cloudflare=solve_cf,
                          real_chrome=real_chrome)
    if exe_path:
        session_kwargs["executable_path"] = exe_path
    return StealthySession(**session_kwargs)


def _worker_fetch(exe_path, solve_cf, real_chrome,
                  url, timeout, adaptive, css_selector):
    """Fetch + extract целиком в одном потоке: сессия создаётся и используется
    здесь же (Playwright sync API привязан к потоку создания — кросс-поток
    запрещён). Одна попытка, без повторных заходов.

    Возвращает (text, extractor, success, error, status_code).
    """
    start_ts = time.time()
    with _open_session(exe_path, solve_cf, real_chrome) as session:
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
            extractor = 'css+adaptive' if adaptive else 'css'
            success = bool(text.strip())
        except Exception as exc:  # noqa: BLE001 — intentional: catch any CSS parsing error and fall back to extract_text()
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
    return text, extractor, success, error, status_code


def crawl_batch(targets, prefix, timeout, adaptive, css_selector, solve_cf, out_dir,
                browser_path=None, real_chrome=False,
                deadline_grace=DEADLINE_GRACE_S):
    """Batch-парсинг URL через StealthySession.

    Изоляция на цель: каждая цель — свой поток + своя сессия/браузер.
    Цена — запуск браузера на цель (~10 сек), зато зависший Cloudflare-цикл
    одной цели не вешает весь батч и не портит соседей.
    (Совместная сессия на батч убрана осознанно: Playwright sync API
    кросс-поток запрещает, а общий дедлайн важнее экономии 10-20×.)

    Жёсткий дедлайн на цель: timeout + deadline_grace (wall-clock).
    По истечении — провал с эскалацией (зависший поток/браузер доживает
    до конца процесса, в общий пул не возвращается).
    """
    results = {}
    deadline = timeout + deadline_grace

    exe_path = _resolve_browser_path(browser_path)
    for target in targets:
        url = target["url"]
        tid = target["id"]
        print(f"[{tid}] {url}", flush=True)
        print(f"    fact   : {target['fact']}", flush=True)
        print(f"    expect : {target.get('expect', '')}", flush=True)

        start_ts = time.time()
        try:
            text, extractor, success, error, status_code = _run_isolated(
                _worker_fetch,
                (exe_path, solve_cf, real_chrome, url, timeout,
                 adaptive, css_selector),
                deadline)
            elapsed = time.time() - start_ts
        except concurrent.futures.TimeoutError:
            elapsed = time.time() - start_ts
            error = (f"deadline {deadline:.0f}s exceeded "
                     f"(fetch limit {timeout}s + grace {deadline_grace}s): "
                     f"Cloudflare-цикл не сошёлся — эскалация на Ур.4/Ур.5")
            extractor = "deadline"
            print(f"    status : DEADLINE — {error}", flush=True)
            text = ""
            success = False
            status_code = None
        except Exception as exc:  # noqa: BLE001 — intentional: catch any fetch error (timeout, connection, etc.) and report
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
        fname = _save_result(target, text, success, error, extractor, prefix, status_code, out_dir)
        print(f"    saved  : {fname}", flush=True)
        
        results[tid] = {
            "fact": target["fact"],
            "url": url,
            "text": text,
            "success": success,
            "error": error,
            "extractor": extractor,
            "status":                 status_code,
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
    ap.add_argument("--out-dir", default=None,
                    help="output directory (default: <repo>/workspace)")
    ap.add_argument("--browser-path", default=None,
                    help="Chromium executable path (default: SCRAPLING_EXECUTABLE_PATH env, then Puppeteer cache autodetect)")
    ap.add_argument("--real-chrome", action="store_true",
                    help="Use installed Google Chrome instead of headless Chromium "
                         "(A/B: иногда проходит managed-Turnstile, который не берёт headless)")
    args = ap.parse_args()
    
    fix_windows_console()
    
    validate_prefix(args.prefix)
    targets = read_targets(Path(args.targets))
    print(f"Loaded {len(targets)} targets from {args.targets}", flush=True)
    out_dir = Path(args.out_dir) if args.out_dir else default_out_dir()
    print(f"Settings: timeout={args.timeout}s, adaptive={args.adaptive}, "
          f"css_selector={args.css_selector}, solve_cloudflare={not args.no_cloudflare}, "
          f"real_chrome={args.real_chrome}, "
          f"deadline={args.timeout + DEADLINE_GRACE_S}s "
          f"(timeout+{DEADLINE_GRACE_S}s grace), "
          f"out-dir={out_dir}", flush=True)
    
    results = crawl_batch(
        targets=targets,
        prefix=args.prefix,
        timeout=args.timeout,
        adaptive=args.adaptive,
        css_selector=args.css_selector,
        solve_cf=not args.no_cloudflare,
        out_dir=out_dir,
        browser_path=args.browser_path,
        real_chrome=args.real_chrome,
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
