#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
factcheck_manual.py — сканер ручных источников (быстрый трек Ур.1 -> Ур.5).

Быстрый режим фактчекинга БЕЗ тяжёлых зависимостей (Crawl4AI/Scrapling не нужны):
    Ур.1   агентский веб-поиск собирает кандидатов-источников
    Ур.5-0 человек проверяет их вручную и скачивает файлы в sources-dir
    этот скрипт программно сверяет скачанное с targets.json (evidence)
    Ур.5   человек выносит финальный вердикт по словарю cascade.md

Скрипт НЕ выносит вердиктов CONFIRMED/REFUTED — только evidence-states
(RETRIEVED_OK / BLOCKED / FAILED / SKIPPED) из pipeline/verdicts.py.
Скачанный Cloudflare-Interstitial честно помечается BLOCKED. Словарь
вердиктов НЕ расширяется; финальное слово — за человеком (Ур.5).

Зависимости: только стандартная библиотека. PDF — опционально через pypdf:
если pypdf не установлен, pdf-файлы помечаются SKIPPED с подсказкой,
скрипт не падает.

Конвенция имён файлов: {id}[_\\-. ]*.{txt|md|html|htm|pdf}
Например: ref01_topol2019.pdf -> цель ref01. Несколько файлов на цель — ок;
файлы, не совпавшие ни с одним id, попадают в orphan-предупреждение.

Использование:
    python pipeline/manual/factcheck_manual.py --targets pipeline/targets.json
    python pipeline/manual/factcheck_manual.py --targets ... --sources-dir workspace/manual

Коды выхода:
    0 — все цели имеют evidence (RETRIEVED_OK), BLOCKED-файлов нет
    1 — есть цель без evidence (нет файлов / все SKIPPED/FAILED) или есть BLOCKED
    2 — ошибка конфигурации (targets не найден / пустой / неверный prefix)
"""

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

# Бутстрап путей: скрипт лежит на уровень глубже остальных фактчекеров
# (pipeline/manual/), поэтому родитель pipeline/ — parents[1], корень репо —
# parents[2]. Оба пути добавляем, чтобы работали обе формы запуска:
# скриптом (python pipeline/manual/factcheck_manual.py) и пакетно
# (from pipeline.manual.factcheck_manual import ...).
_PIPELINE_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (_REPO_ROOT, _PIPELINE_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from common import read_targets, validate_prefix, fix_windows_console, default_out_dir, STOP_WORDS
from pipeline.openalex.factcheck_openalex import extract_doi
from pipeline.verdicts import classify_retrieval, RETRIEVED_OK, BLOCKED, SKIPPED

MAX_TEXT_CHARS = 200_000
DEFAULT_WINDOW = 300
DEFAULT_PREFIX = "man"
DEFAULT_SOURCES_SUBDIR = "manual"   # относительно out-dir: workspace/manual

DOI_TEXT_RE = re.compile(r"10\.\d{4,9}/\S+")
_WS_RE = re.compile(r"\s+")
_STRIP_CHARS = ".,;:()[]«»\"'`"


# =================== ИЗВЛЕЧЕНИЕ ТЕКСТА (stdlib-only) ===================

class _TextExtractor(HTMLParser):
    """HTML -> plain text: пропускаем script/style/noscript/head/title,
    блочные теги превращаем в переводы строк."""

    _SKIP = {"script", "style", "noscript", "head", "title"}
    _BLOCK = {"br", "p", "div", "li", "tr", "table", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._chunks = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BLOCK:
            self._chunks.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0 and data.strip():
            self._chunks.append(data)


def html_to_text(raw):
    """Извлечь plain text из HTML. Некорректный HTML — отдаём как есть."""
    parser = _TextExtractor()
    try:
        parser.feed(raw)
        parser.close()
    except Exception:  # noqa: BLE001 — битый HTML не должен валить прогон
        return raw
    return _WS_RE.sub(" ", " ".join(parser._chunks)).strip()


def load_source_text(path):
    """Прочитать файл источника.

    Возвращает (text | None, extractor | reason):
      extractor: 'txt' | 'md' | 'html' | 'pdf' — текст извлечён;
      reason:    'unsupported' | 'pypdf-not-installed' | 'unreadable' | 'empty'.
    """
    ext = path.suffix.lower()

    if ext == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            return None, "pypdf-not-installed"
        try:
            reader = PdfReader(str(path))
            pages = []
            for page in reader.pages:
                try:
                    pages.append(page.extract_text() or "")
                except Exception:  # noqa: BLE001 — страница без текстового слоя
                    pages.append("")
            text = _WS_RE.sub(" ", "\n".join(pages)).strip()
        except Exception:  # noqa: BLE001 — любой сбой pypdf -> unreadable
            return None, "unreadable"
        return (text, "pdf") if text else (None, "empty")

    if ext in (".html", ".htm"):
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None, "unreadable"
        text = html_to_text(raw)
        return (text, "html") if text else (None, "empty")

    if ext in (".txt", ".md"):
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None, "unreadable"
        text = _WS_RE.sub(" ", raw).strip()
        return (text, ext.lstrip(".")) if text else (None, "empty")

    return None, "unsupported"


# =================== ТЕРМИНЫ И СВЕРКА ===================

def significant_terms(*texts):
    """Значимые слова из fact/expect: >= 4 символов, не стоп-слова (common.STOP_WORDS)."""
    terms = set()
    for text in texts:
        for w in (text or "").lower().split():
            w = w.strip(_STRIP_CHARS + "-–—")
            if len(w) >= 4 and w not in STOP_WORDS:
                terms.add(w)
    return sorted(terms)


def analyze_source(target, path, window):
    """Проанализировать один файл источника против цели.

    Возвращает dict с ключами (по наличию):
      file, size, state, extractor, skip, doi, coverage, quote, quote_terms.
    state — evidence-state из verdicts.py, НЕ вердикт.
    """
    rec = {"file": path.name, "size": path.stat().st_size}
    text, tag = load_source_text(path)

    if text is None:
        rec["skip"] = tag
        rec["state"] = SKIPPED
        return rec

    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS]

    rec["extractor"] = tag
    # Скачанная заглушка (cloudflare-маркеры в тексте) честно -> BLOCKED
    rec["state"] = classify_retrieval(text, None)

    # DOI: сверка DOI цели с DOI, найденным в тексте файла
    doi = extract_doi(target)
    if doi:
        m = DOI_TEXT_RE.search(text)
        if m:
            found = m.group(0).rstrip(".,;:)")
            rec["doi"] = "MATCH" if found == doi else "MISMATCH (" + found + ")"
        else:
            rec["doi"] = "not-found"

    # term-coverage: сколько значимых слов fact/expect встречается в тексте
    terms = significant_terms(target.get("fact"), target.get("expect"))
    if terms:
        low = text.lower()
        hits = [t for t in terms if t in low]
        rec["coverage"] = str(len(hits)) + "/" + str(len(terms)) \
            + " (" + str(100 * len(hits) // len(terms)) + "%)"

        # Лучшая цитата: скользящее окно с максимумом покрытия терминами
        if hits:
            best_start, best_hits = 0, -1
            step = max(1, window // 2)
            for start in range(0, len(low), step):
                seg = low[start:start + window]
                score = sum(1 for t in terms if t in seg)
                if score > best_hits:
                    best_start, best_hits = start, score
            rec["quote"] = " ".join(text[best_start:best_start + window].split())
            rec["quote_terms"] = str(best_hits) + "/" + str(len(terms))
    return rec


# =================== МАППИНГ ФАЙЛОВ НА ЦЕЛИ ===================

def match_files(targets, sources_dir):
    """Разложить файлы sources_dir по целям по префиксу id.

    Конвенция: {id}[_\\-. ]*.{ext}. Длинные id проверяются первыми, чтобы
    ref1 не перехватывает файлы цели ref10. Возвращает (mapping, orphans):
      mapping: dict id -> list[Path]; orphans: list[Path] без совпадения.
    """
    mapping = {t["id"]: [] for t in targets}
    orphans = []
    if not sources_dir.is_dir():
        return mapping, orphans
    ids = sorted(mapping, key=len, reverse=True)
    for path in sorted(sources_dir.iterdir()):
        if not path.is_file():
            continue
        name = path.name
        for tid in ids:
            if name.startswith(tid):
                rest = name[len(tid):]
                if rest == "" or rest[0] in "_-. ":
                    mapping[tid].append(path)
                    break
        else:
            orphans.append(path)
    return mapping, orphans


# =================== ОТЧЁТ ===================

def _save_report(target, records, prefix, out_dir, sources_dir):
    """Сохранить man_{id}.txt — формат шапки как у остальных фактчекеров."""
    fname = Path(out_dir) / (prefix + "_" + target["id"] + ".txt")
    fname.parent.mkdir(parents=True, exist_ok=True)
    success = any(r.get("state") == RETRIEVED_OK for r in records)

    with open(fname, "w", encoding="utf-8") as f:
        f.write("URL: " + target["url"] + "\n")
        f.write("FACT: " + target["fact"] + "\n")
        f.write("EXPECT: " + target.get("expect", "") + "\n")
        f.write("SOURCES-DIR: " + str(sources_dir) + "\n")
        f.write("SUCCESS: " + str(success) + "\n")
        f.write("NOTE: evidence-отчёт, НЕ вердикт. Финальный вердикт — человек (Ур.5), словарь cascade.md\n")
        f.write("\n" + "=" * 70 + "\n")
        if not records:
            f.write("[нет файлов источников — см. конвенцию {id}_*.ext в manual.md]\n")
        for i, r in enumerate(records, 1):
            f.write("\n--- [" + str(i) + "] " + r["file"] + " ---\n")
            f.write("STATE: " + r["state"] + "\n")
            if "skip" in r:
                hint = " (pip install pypdf)" if r["skip"] == "pypdf-not-installed" else ""
                f.write("SKIP: " + r["skip"] + hint + "\n")
            else:
                f.write("EXTRACTOR: " + r["extractor"] + "\n")
                f.write("SIZE: " + str(r["size"]) + "\n")
            if "doi" in r:
                f.write("DOI: " + r["doi"] + "\n")
            if "coverage" in r:
                f.write("COVERAGE: " + r["coverage"] + "\n")
            if "quote" in r:
                f.write("QUOTE-TERMS: " + r["quote_terms"] + "\n")
                f.write("QUOTE:\n" + r["quote"] + "\n")
    return fname


def _hint_for_target(records):
    """Подсказка следующего шага для summary (без слов-вердиктов)."""
    if not records:
        return "файлы не найдены — конвенция {id}_*.ext, см. manual.md"
    if any(r.get("state") == BLOCKED for r in records):
        return "в скачанном маркер блокировки — источник-заглушка, используйте другой способ скачивания"
    if any(r.get("state") == RETRIEVED_OK for r in records):
        return "evidence собран — финальный вердикт за человеком (Ур.5, cascade.md)"
    return "файлы есть, но evidence не извлечён — проверьте форматы/содержимое"


def run_scan(targets, sources_dir, prefix, out_dir, window):
    """Прогнать сканер по всем целям. Печатает прогресс, возвращает код выхода."""
    print("Loaded " + str(len(targets)) + " targets", flush=True)
    print("Settings: sources-dir=" + str(sources_dir) + ", prefix=" + prefix
          + ", out-dir=" + str(out_dir) + ", window=" + str(window), flush=True)

    if not sources_dir.is_dir():
        print("WARNING: sources-dir не найден: " + str(sources_dir)
              + " — все цели останутся без файлов", flush=True)

    mapping, orphans = match_files(targets, sources_dir)
    if orphans:
        print("\nWARNING: orphan-файлы (не совпали ни с одним id):", flush=True)
        for p in orphans:
            print("    " + p.name, flush=True)

    all_records = {}
    for t in targets:
        tid = t["id"]
        files = mapping[tid]
        print("\n[" + tid + "] " + t["url"], flush=True)
        print("    fact   : " + t["fact"], flush=True)
        records = [analyze_source(t, f, window) for f in files]
        all_records[tid] = records
        if not records:
            print("    status : NO FILES", flush=True)
        for i, r in enumerate(records, 1):
            print("    --- [" + str(i) + "] " + r["file"] + " ---", flush=True)
            if "skip" in r:
                print("        skip  : " + r["skip"], flush=True)
            else:
                print("        extract: " + r["extractor"] + "  size=" + str(r["size"]), flush=True)
            print("        state : " + r["state"], flush=True)
            if "doi" in r:
                print("        doi   : " + r["doi"], flush=True)
            if "coverage" in r:
                print("        cover : " + r["coverage"], flush=True)
            if "quote" in r:
                print("        quote : " + r["quote"][:120] + "...", flush=True)
        fname = _save_report(t, records, prefix, out_dir, sources_dir)
        print("    saved  : " + str(fname), flush=True)

    # --- Summary ---
    print("\n" + "=" * 70, flush=True)
    print("SUMMARY (manual scanner — evidence, НЕ вердикты)", flush=True)
    print("=" * 70, flush=True)
    for t in targets:
        records = all_records[t["id"]]
        if any(r.get("state") == RETRIEVED_OK for r in records):
            flag = "EVID"
        elif any(r.get("state") == BLOCKED for r in records):
            flag = "BLKD"
        else:
            flag = "NONE"
        print("  [" + flag + "] " + t["id"] + "  files=" + str(len(records))
              + "  " + _hint_for_target(records), flush=True)
    if orphans:
        print("  orphans: " + str(len(orphans)) + " (см. WARNING выше)", flush=True)

    has_evidence = all(any(r.get("state") == RETRIEVED_OK for r in all_records[t["id"]])
                       for t in targets)
    has_blocked = any(r.get("state") == BLOCKED
                      for records in all_records.values() for r in records)
    return 0 if (has_evidence and not has_blocked) else 1


# =================== MAIN ===================

def main():
    fix_windows_console()

    ap = argparse.ArgumentParser(
        description="factcheck_manual.py — сканер ручных источников (быстрый трек Ур.1 -> Ур.5)",
        epilog=("Коды выхода: 0 — у каждой цели есть evidence (RETRIEVED_OK); 1 — есть цель без evidence (нет файлов / только BLOCKED/SKIPPED); "
                "или есть BLOCKED; 2 — ошибка конфигурации.\n"
                "Скрипт НЕ выносит вердиктов CONFIRMED/REFUTED — только evidence-states; "
                "финальное слово за человеком (Ур.5, словарь cascade.md)."),
    )
    ap.add_argument("--targets", required=True, help="path to JSON with TARGETS list")
    ap.add_argument("--sources-dir", default=None,
                    help="каталог с вручную скачанными файлами (default: <out-dir>/manual)")
    ap.add_argument("--prefix", default=DEFAULT_PREFIX,
                    help="output filename prefix (default: man)")
    ap.add_argument("--out-dir", default=None,
                    help="output directory (default: <repo>/workspace)")
    ap.add_argument("--window", type=int, default=DEFAULT_WINDOW,
                    help="размер окна цитаты-контекста в символах (default: 300)")
    args = ap.parse_args()

    validate_prefix(args.prefix)
    targets = read_targets(Path(args.targets), validate_url_https=False)
    if not targets:
        print("FATAL: список целей пуст", file=sys.stderr)
        sys.exit(2)
    out_dir = Path(args.out_dir) if args.out_dir else default_out_dir()
    sources_dir = Path(args.sources_dir) if args.sources_dir else out_dir / DEFAULT_SOURCES_SUBDIR

    exit_code = run_scan(targets, sources_dir, args.prefix, out_dir, args.window)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
