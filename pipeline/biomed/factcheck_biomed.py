#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
factcheck_biomed.py — PubMed & Europe PMC lookup, Ур.0.7 каскада («BioMed Deep Check»).
Бесплатная проверка биомедицинских статей по PMID и PMCID через NCBI E-utilities и Europe PMC API.

Использование:
    python pipeline/biomed/factcheck_biomed.py --targets pipeline/targets.json --prefix bm --timeout 15

Зависимости: стандартная библиотека Python (urllib.request, json, re, xml).
"""

import argparse
import json
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

# Бутстрап путей
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from pipeline.common import read_targets, validate_prefix, fix_windows_console, default_out_dir, STOP_WORDS

PMID_URL_RE = re.compile(r"(?:pubmed\.ncbi\.nlm\.nih\.gov|ncbi\.nlm\.nih\.gov/pubmed)/(\d+)", re.IGNORECASE)
PMID_EXPECT_RE = re.compile(r"(?:PMID|pmid)[:\s#]*(\d+)", re.IGNORECASE)

PMC_URL_RE = re.compile(r"(?:ncbi\.nlm\.nih\.gov/pmc/articles|europepmc\.org/article/PMC)/(PMC\d+|\d+)", re.IGNORECASE)
PMC_EXPECT_RE = re.compile(r"(?:PMCID|pmcid|PMC)[:\s#]*(PMC\d+|\d+)", re.IGNORECASE)

EUTILS_SUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&id={}&retmode=json"
EUROPE_PMC_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=EXT_ID:{}%20SRC:MED&format=json"
EUROPE_PMC_PMC_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=PMC:{}&format=json"


# =================== ИЗВЛЕЧЕНИЕ PMID / PMC ===================

def extract_pmid(target):
    """Извлечь PMID из URL или поля expect."""
    url = target.get("url", "")
    expect = target.get("expect", "")
    m = PMID_URL_RE.search(url)
    if m:
        return m.group(1)
    m = PMID_EXPECT_RE.search(expect)
    if m:
        return m.group(1)
    m = PMID_EXPECT_RE.search(url)
    if m:
        return m.group(1)
    return None


def extract_pmc(target):
    """Извлечь PMCID из URL или поля expect."""
    url = target.get("url", "")
    expect = target.get("expect", "")
    m = PMC_URL_RE.search(url)
    if m:
        val = m.group(1)
        return val if val.upper().startswith("PMC") else f"PMC{val}"
    m = PMC_EXPECT_RE.search(expect)
    if m:
        val = m.group(1)
        return val if val.upper().startswith("PMC") else f"PMC{val}"
    return None


# =================== ЗАПРОСЫ К NCBI E-UTILITIES / EUROPE PMC ===================

def lookup_pubmed_pmid(pmid, timeout=15):
    """Запросить метаданные статьи по PMID через NCBI E-utilities.
    Возвращает (data: dict | None, error: str | None).
    """
    url = EUTILS_SUMMARY_URL.format(pmid)
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "SplitAndMerge-BioMed/1.0 (mailto:biomed@example.com)"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            doc = json.loads(raw)
            result = doc.get("result", {})
            if pmid in result:
                entry = result[pmid]
                if "error" in entry:
                    return None, f"NCBI Error: {entry['error']}"
                # Нормализация в общий формат
                authors = [a.get("name", "") for a in entry.get("authors", []) if a.get("name")]
                norm = {
                    "id": pmid,
                    "pmid": pmid,
                    "title": entry.get("title", ""),
                    "authors": authors,
                    "first_author": authors[0] if authors else "",
                    "journal": entry.get("source", ""),
                    "pubdate": entry.get("pubdate", ""),
                    "volume": entry.get("volume", ""),
                    "issue": entry.get("issue", ""),
                    "pages": entry.get("pages", ""),
                    "doi": entry.get("articleids", {}).get("doi", "") if isinstance(entry.get("articleids"), dict) else "",
                    "source_api": "NCBI E-utilities"
                }
                # Поиск DOI среди articleids
                if isinstance(entry.get("articleids"), list):
                    for aid in entry.get("articleids"):
                        if aid.get("idtype") == "doi":
                            norm["doi"] = aid.get("value", "")
                        elif aid.get("idtype") == "pmc":
                            norm["pmcid"] = aid.get("value", "")
                return norm, None
            return None, "NOT_FOUND"
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None, "NOT_FOUND"
        return None, f"HTTP {exc.code}"
    except urllib.error.URLError as exc:
        return None, f"NETWORK: {exc.reason}"
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def lookup_europepmc(query_id, is_pmc=False, timeout=15):
    """Запросить метаданные статьи через Europe PMC REST API."""
    if is_pmc:
        pmc_num = query_id.upper().replace("PMC", "")
        url = EUROPE_PMC_PMC_URL.format(pmc_num)
    else:
        url = EUROPE_PMC_URL.format(query_id)
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "SplitAndMerge-BioMed/1.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            doc = json.loads(raw)
            result_list = doc.get("resultList", {}).get("result", [])
            if not result_list:
                return None, "NOT_FOUND"
            entry = result_list[0]
            authors_str = entry.get("authorString", "")
            authors = [a.strip() for a in authors_str.split(",") if a.strip()]
            norm = {
                "id": query_id,
                "pmid": entry.get("pmid", ""),
                "pmcid": entry.get("pmcid", ""),
                "title": entry.get("title", ""),
                "authors": authors,
                "first_author": authors[0] if authors else "",
                "journal": entry.get("journalTitle", ""),
                "pubdate": str(entry.get("pubYear", "")),
                "volume": entry.get("journalVolume", ""),
                "issue": entry.get("issue", ""),
                "pages": entry.get("pageInfo", ""),
                "doi": entry.get("doi", ""),
                "source_api": "Europe PMC"
            }
            return norm, None
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None, "NOT_FOUND"
        return None, f"HTTP {exc.code}"
    except urllib.error.URLError as exc:
        return None, f"NETWORK: {exc.reason}"
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


# =================== КРОСС-ПРОВЕРКА FACT vs METADATA ===================

def check_biomed_fact_match(fact, data):
    """Сравнить fact-строку с биомедицинскими метаданными (автор, ключевые слова названия)."""
    title = (data.get("title") or "").lower()
    first_author = data.get("first_author", "")
    fact_lower = fact.lower()

    checks_passed = []
    checks_failed = []

    # 1. Проверка фамилии автора
    author_surname = first_author.split()[0] if first_author else ""
    if author_surname and len(author_surname) >= 2 and author_surname.lower() in fact_lower:
        checks_passed.append(f"author '{author_surname}' found in fact")
    elif author_surname:
        checks_failed.append(f"author '{author_surname}' NOT in fact")

    # 2. Проверка значимых слов названия
    fact_title_part = fact_lower
    for sep in [" — ", ". ", " —", "— "]:
        if sep in fact_lower:
            fact_title_part = fact_lower.split(sep, 1)[1]
            break

    fact_words = {
        w.strip(".,;:()[]«»\"'") for w in fact_title_part.split()
        if len(w.strip(".,;:()[]«»\"'")) >= 4 and w.strip(".,;:()[]«»\"'").lower() not in STOP_WORDS
    }
    title_words = {w.strip(".,;:()[]«»\"'") for w in title.split() if len(w.strip(".,;:()[]«»\"'")) >= 4}
    matches = fact_words & title_words

    if len(fact_words) >= 3:
        overlap = len(matches) / len(fact_words)
        if overlap >= 0.25:
            checks_passed.append(f"title overlap {overlap:.0%} ({len(matches)}/{len(fact_words)} words)")
        else:
            checks_failed.append(f"title overlap only {overlap:.0%}")
    elif len(fact_words) >= 1:
        if matches:
            checks_passed.append(f"title words match: {matches}")
        else:
            checks_failed.append("no title word overlap")

    is_match = len(checks_passed) > 0
    detail = "; ".join(checks_passed + checks_failed)
    return is_match, detail


# =================== СОХРАНЕНИЕ РЕЗУЛЬТАТА ===================

def save_biomed_result(target, id_val, id_type, data, error, status, prefix, out_dir):
    """Сохранить артефакт workspace/{prefix}_{id}.txt."""
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{prefix}_{target['id']}.txt"

    lines = [
        f"URL: {target.get('url', '')}",
        f"FACT: {target.get('fact', '')}",
        f"EXPECT: {target.get('expect', '')}",
        f"{id_type.upper()}: {id_val}",
        f"STATUS: {status}",
    ]
    if error:
        lines.append(f"ERROR: {error}")
    if data:
        lines.append(f"TITLE: {data.get('title', '')}")
        lines.append(f"AUTHORS: {'; '.join(data.get('authors', []))}")
        lines.append(f"JOURNAL: {data.get('journal', '')}")
        lines.append(f"YEAR: {data.get('pubdate', '')}")
        if data.get("volume"):
            lines.append(f"VOLUME: {data.get('volume')}")
        if data.get("pages"):
            lines.append(f"PAGES: {data.get('pages')}")
        if data.get("doi"):
            lines.append(f"DOI: {data.get('doi')}")
        if data.get("pmcid"):
            lines.append(f"PMCID: {data.get('pmcid')}")
        lines.append(f"API: {data.get('source_api', '')}")

    out_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_file


# =================== ПАКЕТНАЯ ОБРАБОТКА ===================

def batch_lookup_biomed(targets, prefix="bm", timeout=15, out_dir=None, crosscheck=True):
    """Обработать список целей по биомедицинским базам (PubMed / Europe PMC)."""
    if out_dir is None:
        out_dir = default_out_dir()
    out_dir = Path(out_dir)

    results = {}
    for i, t in enumerate(targets):
        tid = t["id"]
        pmid = extract_pmid(t)
        pmc = extract_pmc(t)

        if not pmid and not pmc:
            results[tid] = {"status": "SKIP", "error": "No PMID or PMCID found"}
            continue

        data = None
        error = None
        id_val = pmid or pmc
        id_type = "PMID" if pmid else "PMCID"

        # 1. Попытка через PubMed E-utilities, если есть PMID
        if pmid:
            data, error = lookup_pubmed_pmid(pmid, timeout=timeout)
            # Фолбэк на Europe PMC при сетевых ошибках или 404
            if not data:
                data, error = lookup_europepmc(pmid, is_pmc=False, timeout=timeout)
        else:
            # 2. Попытка через Europe PMC по PMCID
            data, error = lookup_europepmc(pmc, is_pmc=True, timeout=timeout)

        if data:
            if crosscheck:
                is_match, detail = check_biomed_fact_match(t.get("fact", ""), data)
                if is_match:
                    status = "CONFIRMED"
                else:
                    status = "MISMATCH"
                    error = f"Crosscheck failed: {detail}"
            else:
                status = "CONFIRMED"
        else:
            status = "ERROR"

        save_biomed_result(t, id_val, id_type, data, error, status, prefix, out_dir)
        results[tid] = {"status": status, "data": data, "error": error}

        # Вежливый рейт-лимит для NCBI (не более 3 запросов в секунду без ключа)
        time.sleep(0.35)

    return results


# =================== CLI ===================

def main():
    fix_windows_console()
    parser = argparse.ArgumentParser(
        description="factcheck_biomed.py — биомедицинский фактчекинг через PubMed и Europe PMC (Ур.0.7)"
    )
    parser.add_argument("--targets", required=True, help="Путь к JSON-файлу целей")
    parser.add_argument("--prefix", default="bm", help="Префикс выходных файлов (default: bm)")
    parser.add_argument("--timeout", type=int, default=15, help="Таймаут запроса в секундах (default: 15)")
    parser.add_argument("--out-dir", default=None, help="Каталог вывода (default: workspace)")
    parser.add_argument("--no-crosscheck", action="store_true", help="Отключить кросс-проверку факта и метаданных")
    parser.add_argument("--dry-run", action="store_true", help="Показать план без выполнения запросов")

    args = parser.parse_args()
    validate_prefix(args.prefix)

    targets_path = Path(args.targets)
    if not targets_path.is_file():
        print(f"FATAL: Файл targets не найден: {args.targets}", file=sys.stderr)
        sys.exit(2)

    targets = read_targets(targets_path, validate_url_https=False)
    out_dir = Path(args.out_dir) if args.out_dir else default_out_dir()

    biomed_targets = [t for t in targets if extract_pmid(t) or extract_pmc(t)]

    if args.dry_run:
        print(f"=== DRY-RUN: BioMed Deep Check (Ур.0.7) ===")
        print(f"Всего целей: {len(targets)}")
        print(f"Биомедицинских целей (PMID/PMC): {len(biomed_targets)}")
        for t in biomed_targets:
            pmid = extract_pmid(t)
            pmc = extract_pmc(t)
            print(f"  [{t['id']}] PMID={pmid or '—'}, PMC={pmc or '—'} -> {t['url']}")
        sys.exit(0)

    print(f"\n=== Запуск BioMed Deep Check (Ур.0.7): {len(biomed_targets)} целей ===", flush=True)
    results = batch_lookup_biomed(
        targets,
        prefix=args.prefix,
        timeout=args.timeout,
        out_dir=out_dir,
        crosscheck=not args.no_crosscheck
    )

    confirmed = sum(1 for r in results.values() if r["status"] == "CONFIRMED")
    mismatch = sum(1 for r in results.values() if r["status"] == "MISMATCH")
    errors = sum(1 for r in results.values() if r["status"] == "ERROR")
    skipped = sum(1 for r in results.values() if r["status"] == "SKIP")

    print("\n" + "=" * 60)
    print(f"SUMMARY (biomed): CONFIRMED={confirmed}  MISMATCH={mismatch}  ERROR={errors}  SKIP={skipped}")
    print("=" * 60)

    sys.exit(1 if mismatch > 0 else 0)


if __name__ == "__main__":
    main()
