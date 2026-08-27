#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sam.py — авто-каскад веб-фактчекинга (оркестратор водопада).

Фазы исполняются строго сверху вниз по pipeline/docs/cascade.md:
    Ур.0.5 OpenAlex → Ур.2 Crawl4AI → Ур.3 Scrapling
Уровни 1 (researcher-web), 4 (FireCrawl), 5 (человек), 6 (Gemini DeepSearch)
программно недоступны — помечаются handoff. FireCrawl (Ур.4, платный)
автоматически НЕ вызывается НИКОГДА — только рекомендация в отчёте.

Вердикты — словарь Роли 5 (cascade.md, verdicts.py):
    CONFIRMED / REFUTED / UNCERTAIN / BLOCKED
Evidence-states (RETRIEVED_OK / BLOCKED / FAILED / SKIPPED) — только внутри
level_results, они не являются вердиктами.

Коды выхода:
    0 — прогон завершён, REFUTED нет
    1 — прогон завершён, есть REFUTED (гейт остановился на проверке)
    2 — ошибка конфигурации (targets не найден / пустой список / неверные уровни)
"""

import argparse
import asyncio
import datetime
import os
import sys
from pathlib import Path

# Бутстрап: при запуске как скрипта (python pipeline/sam.py) sys.path[0] — каталог
# скрипта (pipeline/), и пакетный импорт pipeline.* не резолвится. Добавляем КОРЕНЬ
# репозитория в sys.path, чтобы работали обе формы запуска: скрипт (__package__ пуст)
# и установленный entry-point `sam` → pipeline.sam:main (__package__ = "pipeline").
_REPO_ROOT = Path(__file__).resolve().parents[1]
if not __package__:
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

from pipeline.common import read_targets, fix_windows_console, default_out_dir
from pipeline.openalex.factcheck_openalex import batch_lookup, extract_doi, _DEFAULT_MAILTO
from pipeline.verdicts import (
    Verdict, VerdictRecord, verdict_from_openalex, classify_retrieval,
    write_json, RETRIEVED_OK, BLOCKED, FAILED,
)

# Формат шапки crawl-файла — как в factcheck_crawl4ai.main_async
TRUNCATE_KEEP_CHARS = 1_500


# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------

def _relpath(p):
    """Относительный путь к workspace-файлу от корня репо (для артефактов)."""
    return os.path.relpath(str(p), str(_REPO_ROOT)).replace("\\", "/")


def _write_crawl_artifact(fname, t, text, success, error, links_str):
    """Записать crawl_{id}.txt (формат шапки — как у factcheck_crawl4ai)."""
    fname.parent.mkdir(parents=True, exist_ok=True)
    with open(fname, "w", encoding="utf-8") as f:
        f.write(f"URL: {t['url']}\n")
        f.write(f"FACT: {t['fact']}\n")
        f.write(f"EXPECT: {t.get('expect', '')}\n")
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


# ---------------------------------------------------------------------------
# Фазы каскада
# ---------------------------------------------------------------------------

def _phase2(candidates, timeout, out_dir):
    """Фаза 2: Crawl4AI (Ур.2). Возвращает dict id -> {text, success, error, links}.

    Любой сбой инфраструктуры (браузер не установлен, краш) деградирует все
    цели фазы в FAILED — sam.py не должен падать, вердикт по матрице станет UNCERTAIN.
    """
    out = {}

    def _fail_all(exc):
        for t in candidates:
            out.setdefault(t["id"], {"text": "", "success": False,
                                     "error": f"{type(exc).__name__}: {exc}", "links": ""})

    async def _run():
        try:
            from pipeline.crawl4ai.factcheck_crawl4ai import AsyncWebCrawler, crawl_one
            crawler = AsyncWebCrawler()
            try:
                await crawler.start()
                for t in candidates:
                    text, success, error, links_str = await crawl_one(crawler, t, timeout)
                    out[t["id"]] = {"text": text, "success": success, "error": error, "links": links_str}
            finally:
                try:
                    await crawler.close()
                except Exception:  # noqa: BLE001 — best-effort cleanup
                    pass
        except Exception as exc:  # noqa: BLE001 — сбой фазы ≠ падение sam.py
            _fail_all(exc)

    try:
        asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001
        _fail_all(exc)
    return out


def _phase3(sc_targets, timeout, out_dir):
    """Фаза 3: Scrapling (Ур.3). crawl_batch сам пишет sc_{id}.txt в out-dir.

    Сбой сессии (браузер недоступен) → все цели фазы деградируют в FAILED.
    """
    try:
        from pipeline.scrapling.factcheck_scrapling import crawl_batch
        return crawl_batch(sc_targets, "sc", timeout, False, None, True, str(out_dir))
    except Exception as exc:  # noqa: BLE001
        return {t["id"]: {"fact": t["fact"], "url": t["url"], "text": "",
                           "success": False, "error": f"{type(exc).__name__}: {exc}",
                           "extractor": "error", "status": None}
                for t in sc_targets}


# ---------------------------------------------------------------------------
# Оркестрация
# ---------------------------------------------------------------------------

def run_cascade(targets, exec_levels, args, out_dir):
    """Исполнить фазы водопада и вернуть список VerdictRecord (по матрице verdicts.py)."""
    oa_results = {}
    if "0.5" in exec_levels:
        doi_targets = [t for t in targets if extract_doi(t)]
        if doi_targets:
            print(f"\n=== Фаза 0.5: OpenAlex (Ур.0.5) — {len(doi_targets)} целей с DOI ===", flush=True)
            oa_results = batch_lookup(doi_targets, "oa", args.timeout_oa, args.mailto,
                                      str(out_dir), crosscheck=not args.no_crosscheck)

    records = []
    pending = {}   # id -> VerdictRecord (ещё не решён — эскалируется)

    for t in targets:
        tid = t["id"]
        oa = oa_results.get(tid)
        rec = VerdictRecord(id=tid, fact=t["fact"], url=t["url"],
                            verdict=Verdict.UNCERTAIN, reason="", needs_review=False)
        if oa is not None:
            rec.levels_tried.append("0.5")
            rec.level_results["0.5"] = {"status": oa.get("status"), "error": oa.get("error")}
            oa_art = out_dir / f"oa_{tid}.txt"
            if oa_art.is_file():
                rec.artifacts.append(_relpath(oa_art))
            v = verdict_from_openalex(oa.get("status"))
            if v is Verdict.CONFIRMED:
                rec.verdict = Verdict.CONFIRMED
                rec.reason = "OpenAlex CONFIRMED — DOI подтверждён, эскалация не нужна"
                records.append(rec)
                continue
            if v is Verdict.REFUTED:
                rec.verdict = Verdict.REFUTED
                rec.reason = "OpenAlex MISMATCH — факт не соответствует метаданным статьи, сверить с исходником вручную"
                rec.needs_review = True
                records.append(rec)
                continue
            # ERROR (в т.ч. NOT_FOUND, HTTP 429)/SKIP → эскалация в фазу 2
        pending[tid] = rec

    # --- Фаза 2: Crawl4AI ---
    if "2" in exec_levels and pending:
        print(f"\n=== Фаза 2: Crawl4AI (Ур.2) — {len(pending)} целей ===", flush=True)
        candidates = [t for t in targets if t["id"] in pending]
        p2 = _phase2(candidates, args.timeout_crawl, out_dir)
        for t in candidates:
            tid = t["id"]
            rec = pending[tid]
            r = p2.get(tid, {})
            text = r.get("text") or ""
            error = r.get("error")
            retrieval = classify_retrieval(text, error)
            rec.levels_tried.append("2")
            rec.level_results["2"] = {
                "retrieval": retrieval,
                "success": r.get("success"),
                "error": error,
                "length": len(text),
            }
            fname = out_dir / f"crawl_{tid}.txt"
            _write_crawl_artifact(fname, t, text, r.get("success", False), error, r.get("links"))
            rec.artifacts.append(_relpath(fname))
            print(f"    retrieval: {retrieval}  artifact: {_relpath(fname)}", flush=True)

    # --- Фаза 3: Scrapling (только цели с FAILED/BLOCKED фазы 2) ---
    if "3" in exec_levels:
        sc_ids = [tid for tid, rec in pending.items()
                  if rec.level_results.get("2", {}).get("retrieval") in (FAILED, BLOCKED)]
        if sc_ids:
            print(f"\n=== Фаза 3: Scrapling (Ур.3) — {len(sc_ids)} целей ===", flush=True)
            sc_targets = [t for t in targets if t["id"] in sc_ids]
            sc_results = _phase3(sc_targets, args.timeout_scrap, out_dir)
            for tid in sc_ids:
                rec = pending[tid]
                r = sc_results.get(tid, {})
                text = r.get("text") or ""
                error = r.get("error")
                retrieval = classify_retrieval(text, error)
                rec.levels_tried.append("3")
                rec.level_results["3"] = {
                    "retrieval": retrieval,
                    "success": r.get("success"),
                    "error": error,
                    "extractor": r.get("extractor"),
                    "status": r.get("status"),
                }
                sc_art = out_dir / f"sc_{tid}.txt"
                if sc_art.is_file():
                    rec.artifacts.append(_relpath(sc_art))
                print(f"    retrieval: {retrieval}  artifact: {_relpath(sc_art)}", flush=True)

    # --- Финальные вердикты по матрице verdicts.py (A5) ---
    for tid, rec in pending.items():
        states = [rec.level_results[lv].get("retrieval")
                  for lv in ("2", "3") if lv in rec.level_results]
        states = [s for s in states if s is not None]
        if any(s == RETRIEVED_OK for s in states):
            rec.verdict = Verdict.UNCERTAIN
            rec.reason = "evidence собран, требуется анализ агентом"
        elif states and all(s == BLOCKED for s in states):
            rec.verdict = Verdict.BLOCKED
            rec.reason = "все попытки краула заблокированы — Ур.4 FireCrawl платно ИЛИ Ур.5 человек"
        else:
            rec.verdict = Verdict.UNCERTAIN
            rec.reason = "требуется researcher-web, Ур.1"
        rec.needs_review = True
        records.append(rec)

    return records


def _next_step(r):
    """Рекомендуемый следующий шаг по вердикту (для sam_report.md)."""
    if r.verdict is Verdict.CONFIRMED:
        return "—"
    if r.verdict is Verdict.REFUTED:
        return "сверить с исходником вручную"
    if r.verdict is Verdict.BLOCKED:
        return "Ур.4 платно или Ур.5 вручную"
    # UNCERTAIN
    has_evidence = any(lr.get("retrieval") == RETRIEVED_OK for lr in r.level_results.values())
    return "анализ агентом/человеком" if has_evidence else "передать researcher-web (Ур.1)"


def write_report(records, out_dir, args, exec_levels, handoff_levels):
    """Человекочитаемый отчёт sam_report.md (секции по вердиктам + легенда)."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    L = ["# Отчёт авто-каскада (sam.py)", ""]
    L.append(f"- **Дата:** {now}")
    L.append(f"- **Настройки:** targets=`{args.targets}`, out-dir=`{out_dir}`, "
             f"timeout-oa={args.timeout_oa}, timeout-crawl={args.timeout_crawl}, "
             f"timeout-scrap={args.timeout_scrap}, levels=`{','.join(exec_levels + handoff_levels)}`")
    L.append("")
    for v in (Verdict.CONFIRMED, Verdict.REFUTED, Verdict.UNCERTAIN, Verdict.BLOCKED):
        group = [r for r in records if r.verdict is v]
        L.append(f"## {v.value} ({len(group)})")
        L.append("")
        if not group:
            L.append("_нет_")
            L.append("")
            continue
        L.append("| id | url | reason | артефакты | следующий шаг |")
        L.append("|---|---|---|---|---|")
        for r in group:
            art = ", ".join(r.artifacts) if r.artifacts else "—"
            L.append(f"| {r.id} | {r.url} | {r.reason} | {art} | {_next_step(r)} |")
        L.append("")
    L.append("## Легенда")
    L.append("")
    cascade_rel = os.path.relpath(str(_REPO_ROOT / "pipeline" / "docs" / "cascade.md"), str(out_dir)).replace("\\", "/")
    L.append(f"- **Вердикты** (`CONFIRMED` / `REFUTED` / `UNCERTAIN` / `BLOCKED`) — итог по факту, словарь Роли 5: [`{cascade_rel}`]({cascade_rel}).")
    L.append("- **Evidence-states** (`RETRIEVED_OK` / `BLOCKED` / `FAILED` / `SKIPPED`) — только статусы извлечения внутри `level_results` (`sam_verdicts.json`). Успешное извлечение текста (`SUCCESS: True`) НЕ превращается в `CONFIRMED` — подтверждение даёт только программная проверка OpenAlex или человек/агент. НИКОГДА не выдумывать подтверждения.")
    L.append("- Низкоуровневые статусы скриптов (`CONFIRMED`/`MISMATCH`/`ERROR`/`SKIP` на Ур.0.5) — не финальные вердикты.")
    if any(r.verdict is Verdict.BLOCKED for r in records):
        L.append("- ⚠️ Рекомендован Ур.4 (FireCrawl, платно) — автоматически НЕ вызывался. При ручном использовании после сеанса выполни `firecrawl credit-usage` и запиши цифры в `results.md` (knowledge.md §0.5).")
    L.append("")
    p = out_dir / "sam_report.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    return p


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    # fix_windows_console() ДО parse_args: argparse печатает --help в stdout и
    # падает на cp1251-консоли раньше, чем отработал бы unicode-fix (известная мина).
    fix_windows_console()

    ap = argparse.ArgumentParser(
        description="sam.py — авто-каскад веб-фактчекинга (Ур.0.5 → Ур.2 → Ур.3 по cascade.md)",
        epilog=("Коды выхода: 0 — нет REFUTED; 1 — есть REFUTED; 2 — ошибка конфигурации.\n"
                "Уровни 1/4/5/6 программно недоступны (handoff); FireCrawl (Ур.4) автоматически НЕ вызывается."),
    )
    ap.add_argument("--targets", required=True, help="path to JSON with TARGETS list")
    ap.add_argument("--out-dir", default=None, help="output directory (default: <repo>/workspace)")
    ap.add_argument("--timeout-oa", type=int, default=15,
                    help="OpenAlex per-request timeout (s) (default: 15)")
    ap.add_argument("--timeout-crawl", type=int, default=45,
                    help="Crawl4AI per-URL timeout (s) (default: 45)")
    ap.add_argument("--timeout-scrap", type=int, default=90,
                    help="Scrapling per-URL timeout (s) (default: 90)")
    ap.add_argument("--levels", default="0.5,2,3",
                    help="cascade levels to run, comma-separated subset of 0.5,2,3; 1/4/5/6 = handoff (default: 0.5,2,3)")
    ap.add_argument("--mailto", default=_DEFAULT_MAILTO,
                    help=f"email for OpenAlex Polite Pool (default: {_DEFAULT_MAILTO})")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the plan without executing anything")
    ap.add_argument("--no-crosscheck", action="store_true",
                    help="Disable fact-vs-metadata cross-check in OpenAlex phase (all existing DOIs → CONFIRMED)")
    args = ap.parse_args()

    # --- уровни ---
    raw_levels = [x.strip() for x in args.levels.split(",") if x.strip()]
    EXEC_LEVELS = ("0.5", "2", "3")
    HANDOFF_LEVELS = ("1", "4", "5", "6")
    unknown = [lv for lv in raw_levels if lv not in EXEC_LEVELS and lv not in HANDOFF_LEVELS]
    if unknown:
        print(f"FATAL: неизвестные уровни: {unknown} (допустимые: 0.5,2,3; 1/4/5/6 — handoff)", file=sys.stderr)
        sys.exit(2)
    exec_levels = [lv for lv in EXEC_LEVELS if lv in raw_levels]   # канонический порядок водопада
    handoff_levels = [lv for lv in HANDOFF_LEVELS if lv in raw_levels]

    # --- конфигурация ---
    targets_path = Path(args.targets)
    if not targets_path.is_file():
        print(f"FATAL: файл targets не найден: {args.targets}", file=sys.stderr)
        sys.exit(2)
    targets = read_targets(targets_path, validate_url_https=False)
    if not targets:
        print("FATAL: список целей пуст", file=sys.stderr)
        sys.exit(2)
    out_dir = Path(args.out_dir) if args.out_dir else default_out_dir()

    # --- dry-run: только план, ничего не выполнять (каталог вывода НЕ создаётся) ---
    if args.dry_run:
        doi_count = sum(1 for t in targets if extract_doi(t))
        print("=== DRY-RUN: план авто-каскада (sam.py) ===", flush=True)
        print(f"targets : {len(targets)} целей из {args.targets}", flush=True)
        print(f"out-dir : {out_dir}", flush=True)
        print(f"уровни  : исполняемые {','.join(exec_levels) or '—'} | handoff {','.join(handoff_levels) or '—'}", flush=True)
        print(f"Фаза 0.5 (OpenAlex): {doi_count} целей с DOI → batch_lookup; CONFIRMED закрываются, MISMATCH → REFUTED, ERROR/SKIP → выше", flush=True)
        if "2" in exec_levels:
            print("Фаза 2 (Crawl4AI): все не-CONFIRMED/не-REFUTED цели; маркеры блокировки в тексте → Ур.3", flush=True)
        else:
            print("Фаза 2 (Crawl4AI): отключена (уровень не в --levels)", flush=True)
        if "3" in exec_levels:
            print("Фаза 3 (Scrapling): цели с FAILED/BLOCKED фазы 2", flush=True)
        else:
            print("Фаза 3 (Scrapling): отключена (уровень не в --levels)", flush=True)
        print("Ожидаемые вердикты (матрица verdicts.py): CONFIRMED / REFUTED / UNCERTAIN / BLOCKED", flush=True)
        print("Коды выхода: 0 — нет REFUTED; 1 — есть REFUTED; 2 — ошибка конфигурации", flush=True)
        sys.exit(0)

    # --- боевой прогон ---
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Loaded {len(targets)} targets from {args.targets}", flush=True)
    records = run_cascade(targets, exec_levels, args, out_dir)

    verdicts_path = out_dir / "sam_verdicts.json"
    write_json(records, verdicts_path)
    report_path = write_report(records, out_dir, args, exec_levels, handoff_levels)

    print("\n" + "=" * 70, flush=True)
    print("SUMMARY (sam.py)", flush=True)
    print("=" * 70, flush=True)
    for v in (Verdict.CONFIRMED, Verdict.REFUTED, Verdict.UNCERTAIN, Verdict.BLOCKED):
        print(f"{v.value}={sum(1 for r in records if r.verdict is v)}", end="  ", flush=True)
    print(f"TOTAL={len(records)}", flush=True)
    for r in records:
        print(f"  [{r.verdict.value}] {r.id}  {r.url}  {r.reason}", flush=True)
    print(f"verdicts: {verdicts_path}", flush=True)
    print(f"report  : {report_path}", flush=True)

    has_refuted = any(r.verdict is Verdict.REFUTED for r in records)
    sys.exit(1 if has_refuted else 0)


if __name__ == "__main__":
    main()
