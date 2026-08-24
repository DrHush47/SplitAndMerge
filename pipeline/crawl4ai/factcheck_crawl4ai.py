#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
factcheck_crawl4ai.py (v5)
===========================

Обобщённый фактчек-краулер на базе Crawl4AI.

Использование:
    python factcheck_crawl4ai.py --targets targets.json [--prefix crawl] [--timeout 45] [--no-cache] [--js-code "..."] [--session my-session]

Изменения v4->v5 (аудит 2026-07-16):
  - CacheMode.ENABLED по умолчанию (--no-cache для отключения). Экономит время на повторных URL.
  - .links вывод в выходной файл — кросс-проверка всех ссылок на странице.
  - --js-code для инъекции JS (решает EMPTY на JS-тяжёлых сайтах).
  - --session для сохранения кук между запросами.

Изменения v2->v3 (ответ на второй code-review):
  - --prefix: явный гард списком на '.', '..', '...' и пути-разделители,
    плюс регулярка как belt-and-suspenders.
  - TRUNCATE_KEEP_CHARS 500 -> 1500 (достаточно для Cloudflare заглушки BMJ).
  - Truncate: оригинальная длина сохраняется в отдельной переменной
    (без зависимости от порядка вычисления Python в f-string).

Изменения v3->v4:
  - Вывод файлов в папку скрипта (crawl4ai/), а не в CWD.
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Shared pipeline utilities (pipeline/common.py)
sys.path.insert(0, str(Path(__file__).parent.parent))
from common import read_targets, validate_prefix, fix_windows_console

from crawl4ai import AsyncWebCrawler, CacheMode

MAX_TEXT_CHARS = 200_000
TRUNCATE_KEEP_CHARS = 1_500


async def crawl_one(crawler, target, timeout, js_code=None, session_id=None, use_cache=True):
    url = target["url"]
    print(f"[{target['id']}] {url}", flush=True)
    print(f"    fact   : {target['fact']}", flush=True)
    print(f"    expect : {target.get('expect', '')}", flush=True)

    kwargs = {}
    if js_code:
        kwargs["js_code"] = js_code
    if session_id:
        kwargs["session_id"] = session_id
    if use_cache:
        kwargs["cache_mode"] = CacheMode.ENABLED
    else:
        kwargs["cache_mode"] = CacheMode.BYPASS

    try:
        result = await asyncio.wait_for(crawler.arun(url, **kwargs), timeout=timeout)
    except asyncio.TimeoutError:
        msg = f"crawl timeout after {timeout}s"
        print(f"    status : TIMEOUT ({msg})", flush=True)
        return "", False, msg, ""
    except Exception as exc:
        msg = f"{type(exc).__name__}: {exc}"
        print(f"    status : ERROR ({msg})", flush=True)
        return "", False, msg, ""
    text = getattr(result, "markdown", "") or ""
    links_raw = getattr(result, "links", None) or []
    # Crawl4AI links can be: list-of-dicts, list-of-strs, or dict {url: text}
    links_parts = []
    if isinstance(links_raw, dict):
        for url, link_text in links_raw.items():
            links_parts.append(f"  {url} — {str(link_text)[:80]}")
    else:
        try:
            links_raw = list(links_raw)[:50]
        except (TypeError, KeyError):
            links_raw = []
        for link in links_raw:
            if isinstance(link, str):
                links_parts.append(f"  {link}")
            elif isinstance(link, dict):
                href = link.get('href') or link.get('url') or ''
                txt = link.get('text') or link.get('title') or ''
                links_parts.append(f"  {href} — {txt[:80]}")
    links_str = "\n".join(links_parts) if links_parts else ""
    links_count = len(links_parts)
    original_len = len(text)
    if original_len > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS] + f"\n\n[TRUNCATED from {original_len} chars to {MAX_TEXT_CHARS}]"
    success = bool(text.strip())
    print(f"    status : {'OK' if success else 'EMPTY'}  length={original_len}  links={links_count}", flush=True)
    return text, success, None, links_str


async def main_async(args):
    fix_windows_console()
    targets = read_targets(Path(args.targets))
    print(f"Loaded {len(targets)} targets from {args.targets}", flush=True)

    results = {}
    async with AsyncWebCrawler() as crawler:
        for t in targets:
            text, success, error, links_str = await crawl_one(crawler, t, args.timeout, args.js_code, args.session, not args.no_cache)
            results[t["id"]] = {
                "fact":    t["fact"],
                "url":     t["url"],
                "expect":  t.get("expect", ""),
                "text":    text,
                "success": success,
                "error":   error,
            }
            fname = Path(__file__).parent / f"{args.prefix}_{t['id']}.txt"
            fname.parent.mkdir(parents=True, exist_ok=True)
            with open(fname, "w", encoding="utf-8") as f:
                f.write(f"URL: {t['url']}\n")
                f.write(f"FACT: {t['fact']}\n")
                f.write(f"EXPECT: {t.get('expect','')}\n")
                f.write(f"SUCCESS: {success}\n")
                if error:
                    f.write(f"ERROR: {error}\n")
                    f.write("\n" + "=" * 70 + "\n")
                    f.write(text[:TRUNCATE_KEEP_CHARS] if text else "")
                else:
                    f.write("\n" + "=" * 70 + "\n")
                    f.write(text)
                if links_str:
                    f.write("\n\n--- LINKS ---\n")
                    f.write(links_str)
                    f.write("\n")
            print(f"    saved  : {fname}", flush=True)

    print("\n" + "=" * 70, flush=True)
    print("SUMMARY", flush=True)
    print("=" * 70, flush=True)
    ok = sum(1 for r in results.values() if r["success"])
    print(f"OK={ok}  FAIL={len(results)-ok}  TOTAL={len(results)}", flush=True)
    for tid, r in results.items():
        flag = "OK  " if r["success"] else "FAIL"
        errmsg = f"  err={r['error']!r}" if r["error"] else ""
        print(f"  [{flag}] {tid}  {r['url']}{errmsg}", flush=True)


def main():
    ap = argparse.ArgumentParser(description="Crawl4AI fact-checker (batch runner)")
    ap.add_argument("--targets",  required=True, help="path to JSON with TARGETS list")
    ap.add_argument("--prefix",   default="crawl", help="output filename prefix")
    ap.add_argument("--timeout",  type=int, default=45, help="per-URL crawl timeout (s)")
    ap.add_argument("--no-cache", action="store_true", help="disable cache (default: cache ON)")
    ap.add_argument("--js-code",  default=None, help="JavaScript to inject after page load")
    ap.add_argument("--session",  default=None, help="Session ID for cookie persistence across URLs")
    args = ap.parse_args()
    validate_prefix(args.prefix)
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("Interrupted by user", file=sys.stderr)


if __name__ == "__main__":
    main()
