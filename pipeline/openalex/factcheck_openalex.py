#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
factcheck_openalex.py (v2) — OpenAlex DOI lookup, Ур.0.5 каскада.
Бесплатная (CC0) проверка DOI через REST API.

Использование:
    python scripts/factcheck_openalex.py --targets targets.json --prefix oa --timeout 15

Зависимости: только стандартная библиотека (urllib.request).
"""

import argparse
import json
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

# Import shared utilities from scripts/common.py
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (
    read_targets, validate_prefix, fix_windows_console, default_out_dir,
    STOP_WORDS, transliterate_cyrillic, has_cyrillic, has_word_token,
    match_cognate_word,
)

DOI_URL_RE = re.compile(r"doi\.org/(10\.[^/?#]+/[^/?#]+)")
DOI_EXPECT_RE = re.compile(r"(?:DOI|doi)\s*(10\.[^\s,;)\]]+)", re.IGNORECASE)
OPENALEX_URL = "https://api.openalex.org/works/https://doi.org/{}"
_DEFAULT_MAILTO = "factcheck@example.com"


# =================== ИЗВЛЕЧЕНИЕ DOI ===================

def extract_doi(target):
    """Извлечь DOI из URL или поля expect целевого объекта."""
    url = target.get("url", "")
    expect = target.get("expect", "")
    m = DOI_URL_RE.search(url)
    if m:
        return m.group(1)
    m = DOI_EXPECT_RE.search(expect)
    if m:
        return m.group(1).rstrip(".,;:)]")
    return None


# =================== ЗАПРОС К OPENALEX ===================

def lookup_doi(doi, timeout, mailto):
    """Запросить метаданные работы по DOI через OpenAlex REST API.
    Возвращает (data: dict | None, error: str | None)."""
    url = OPENALEX_URL.format(doi) + f"?mailto={mailto}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "factcheck-openalex/2.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw), None
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None, "NOT_FOUND"
        return None, f"HTTP {exc.code}"
    except urllib.error.URLError as exc:
        return None, f"NETWORK: {exc.reason}"
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def get_first_author_surname(data):
    """Извлечь фамилию первого автора из OpenAlex.

    Пробует обе стратегии: Western order (parts[-1]) и East-Asian order (parts[0]).
    Если найденное слово не найдено в fact — возвращает пустую строку;
    check_fact_match сам проверит вхождение.
    """
    authors = data.get("authorships", [])
    if not authors:
        return ""
    name = authors[0].get("author", {}).get("display_name", "")
    if not name:
        return ""
    parts = name.split()
    if len(parts) == 1:
        return parts[0]
    # Возвращаем кортеж: (western, eastern) — check_fact_match проверит оба
    return (parts[-1], parts[0]) if len(parts) >= 2 else (name,)


def format_authors(data):
    """Форматировать список авторов из ответа OpenAlex."""
    authors = data.get("authorships", [])
    names = []
    for a in authors[:5]:
        name = a.get("author", {}).get("display_name", "")
        if name:
            names.append(name)
    suffix = " et al." if len(authors) > 5 else ""
    return "; ".join(names) + suffix


# =================== КРОСС-ПРОВЕРКА FACT vs METADATA ===================

def _extract_author_surname_strict(display_name: str) -> str:
    """Извлечь только фамилию из display_name OpenAlex, не путая с личным именем.

    Форматы OpenAlex:
      - 'Nikita S. Popov' / 'S. A. Donskov' → 'Popov' / 'Donskov' (последний токен)
      - 'Donskov, S. A.' → 'Donskov' (инвертированная запись с запятой)
      - 'Topol' → 'Topol'
    """
    name = (display_name or "").strip()
    if not name:
        return ""
    parts = name.split()
    if len(parts) == 1:
        return parts[0].strip(".,")
    if parts[0].endswith(","):
        return parts[0].strip(".,")
    return parts[-1].strip(".,")


def classify_fact_match(fact, data):
    """Сравнить fact-строку с метаданными OpenAlex (включая RU ↔ EN транслитерацию).

    Возвращает (status: str, detail: str), где status — один из:
      - "CONFIRMED":
          * в одном алфавите (EN↔EN): совпал первый автор (целым токеном) и/или заголовок;
          * при языковом барьере (RU fact vs EN title): требуется сильное подтверждение —
            либо первый автор (фамилия токеном) + >=1 совпавшее слово заголовка,
            либо соавтор (фамилия токеном) + >=2 совпавших слова заголовка,
            либо >=2 совпавших слова заголовка при overlap >= 30%.
            Одиночное совпадение автора/соавтора без темы или 1 случайный корень НЕ подтверждают.
      - "UNCERTAIN": языковой барьер или слабое совпадение (требуется ручная сверка
                     или лёгкий фетчер, а не ложный CONFIRMED и не ложный MISMATCH).
      - "MISMATCH":  ни автор, ни заголовок не совпали в одном алфавите.

    Эмпирическое обоснование:
      - Тест 27 источников (2026-07-19): DOI 10.1371/journal.pone.0153335 реален,
        но fact не совпадает со статьёй → MISMATCH.
      - Сессия 2026-11-19 (русскоязычные статьи ВАК с DOI в OpenAlex): кириллица в fact
        против латиницы OpenAlex давала 7/7 ложных MISMATCH; RU↔EN сопоставление
        по токенам фамилий, точным/префиксным когнатам и мягкому UNCERTAIN устраняет
        и ложные MISMATCH, и ложные CONFIRMED.
    """
    title = (data.get("title") or "").lower()
    surname = get_first_author_surname(data)  # может быть str или tuple (совместимость EN↔EN)
    fact_lower = fact.lower()
    fact_cyrillic = has_cyrillic(fact)
    fact_translit = transliterate_cyrillic(fact_lower) if fact_cyrillic else fact_lower
    lang_barrier = fact_cyrillic and bool(title) and not has_cyrillic(title)

    checks_passed = []
    checks_failed = []

    # Проверка 1: автор (раздельно: первый автор vs соавтор; строго по границам токенов)
    if isinstance(surname, tuple):
        surnames = list(surname)
    else:
        surnames = [surname] if surname else []

    first_author_matched = False
    coauthor_matched = False
    authorships = data.get("authorships", [])

    if not fact_cyrillic:
        for s in surnames:
            if s and len(s) >= 2 and has_word_token(s, fact_lower):
                checks_passed.append(f"author '{s}' found in fact")
                first_author_matched = True
                break
    else:
        first_display = (
            (authorships[0].get("author") or {}).get("display_name", "")
            if authorships else ""
        )
        first_sn = _extract_author_surname_strict(first_display)
        if first_sn and len(first_sn) >= 2:
            if has_word_token(first_sn, fact_lower):
                checks_passed.append(f"author '{first_sn}' found in fact")
                first_author_matched = True
            elif has_word_token(first_sn, fact_translit):
                checks_passed.append(f"author '{first_sn}' found in fact (translit)")
                first_author_matched = True

        # Соавторы проверяются только по фамилии (не по личному имени) и только целым токеном
        if not first_author_matched:
            for au in authorships[1:]:
                aname = (au.get("author") or {}).get("display_name", "")
                cs = _extract_author_surname_strict(aname)
                if len(cs) >= 3:
                    if has_word_token(cs, fact_lower):
                        checks_passed.append(f"co-author '{cs}' found in fact")
                        coauthor_matched = True
                        break
                    if has_word_token(cs, fact_translit):
                        checks_passed.append(f"co-author '{cs}' found in fact (translit)")
                        coauthor_matched = True
                        break

    if not first_author_matched and not coauthor_matched and surnames:
        checks_failed.append(f"authors {surnames} NOT in fact")

    # Проверка 2: значимые слова из fact в title OpenAlex (отдельно от автора)
    fact_title_part = fact_lower
    for sep in [" — ", ". ", " —", "— "]:
        if sep in fact_lower:
            fact_title_part = fact_lower.split(sep, 1)[1]
            break

    stop_words = STOP_WORDS  # общий словарь из pipeline/common.py
    fact_words = {
        w.strip(".,;:()[]«»\"'") for w in fact_title_part.split()
        if len(w.strip(".,;:()[]«»\"'")) >= 4
        and w.strip(".,;:()[]«»\"'").lower() not in stop_words
    }

    title_words = {w.strip(".,;:()[]«»\"'") for w in title.split()}
    title_words = {w for w in title_words if w}

    matches = set(fact_words & title_words)
    # При языковом барьере (RU fact vs EN title) сверяем через общий строгий матчер когнатов
    if lang_barrier:
        for fw in fact_words - matches:
            if match_cognate_word(fw, title_words):
                matches.add(fw)

    title_any_match = bool(matches)
    title_strong_match = False

    if len(fact_words) >= 3:
        overlap = len(matches) / len(fact_words)
        if lang_barrier:
            title_strong_match = len(matches) >= 2 and overlap >= 0.3
        else:
            title_strong_match = overlap >= 0.3
        if title_strong_match:
            checks_passed.append(f"title overlap {overlap:.0%} ({len(matches)}/{len(fact_words)} words)")
        else:
            checks_failed.append(f"title overlap only {overlap:.0%} ({len(matches)}/{len(fact_words)} words)")
    elif len(fact_words) >= 1:
        if lang_barrier:
            title_strong_match = len(matches) >= 2
        else:
            title_strong_match = bool(matches)
        if title_strong_match:
            checks_passed.append(f"title words match: {matches}")
        elif matches:
            checks_failed.append(f"weak title match under language barrier ({len(matches)} word: {matches})")
        else:
            checks_failed.append(f"no title word overlap (fact words: {fact_words})")

    detail = "; ".join(checks_passed + checks_failed)

    # Классификация вердикта с раздельным учётом автора и заголовка
    if lang_barrier:
        if title_strong_match:
            return "CONFIRMED", detail
        if first_author_matched and title_any_match:
            return "CONFIRMED", detail
        if coauthor_matched and len(matches) >= 2:
            return "CONFIRMED", detail
        if first_author_matched or coauthor_matched:
            return "UNCERTAIN", f"weak cross-language match (author matched without title confirmation); {detail}"
        if title_any_match:
            return "UNCERTAIN", f"weak cross-language match (insufficient title overlap); {detail}"
        return "UNCERTAIN", f"language barrier (Cyrillic fact vs English metadata); {detail}"

    if first_author_matched or title_strong_match:
        return "CONFIRMED", detail
    if coauthor_matched and title_any_match:
        return "CONFIRMED", detail
    if coauthor_matched:
        return "UNCERTAIN", f"co-author only match without title overlap; {detail}"
    return "MISMATCH", detail


def check_fact_match(fact, data):
    """Обратно совместимая обёртка над classify_fact_match: возвращает (is_match: bool, detail: str)."""
    status, detail = classify_fact_match(fact, data)
    return status == "CONFIRMED", detail


def format_biblio(data):
    """Форматировать библиографические данные."""
    loc = (data.get("primary_location") or {})
    source = loc.get("source") or {}
    biblio = loc.get("biblio") or {}
    journal = source.get("display_name", "?")
    year = data.get("publication_year", "?")
    volume = biblio.get("volume")
    first_page = biblio.get("first_page")
    last_page = biblio.get("last_page")
    parts = [f"Journal: {journal}", f"Year: {year}"]
    if volume:
        parts.append(f"Volume: {volume}")
    if first_page:
        pages = first_page
        if last_page:
            pages += f"-{last_page}"
        parts.append(f"Pages: {pages}")
    return ", ".join(parts)


# =================== СОХРАНЕНИЕ РЕЗУЛЬТАТА ===================

def _save_result(target, doi, data, error, status, prefix, out_dir):
    """Сохранить результат в {out_dir}/{prefix}_{id}.txt."""
    fname = Path(out_dir) / f"{prefix}_{target['id']}.txt"
    fname.parent.mkdir(parents=True, exist_ok=True)

    with open(fname, "w", encoding="utf-8") as f:
        f.write(f"URL: {target['url']}\n")
        f.write(f"FACT: {target['fact']}\n")
        f.write(f"EXPECT: {target.get('expect', '')}\n")
        f.write(f"DOI: {doi or 'N/A'}\n")
        f.write(f"STATUS: {status}\n")
        f.write(f"SUCCESS: {status == 'CONFIRMED'}\n")
        if status == "MISMATCH":
            f.write(f"MISMATCH: Fact does not match article metadata\n")
        if error:
            f.write(f"ERROR: {error}\n")
        f.write("\n" + "=" * 70 + "\n")
        if data:
            title = data.get("title", "?")
            authors = format_authors(data)
            biblio = format_biblio(data)
            oa_doi = data.get("doi", "?")
            doi_url = oa_doi.replace("https://doi.org/", "") if oa_doi else "?"
            f.write(f"OpenAlex Title      : {title}\n")
            f.write(f"OpenAlex Authors     : {authors}\n")
            f.write(f"OpenAlex DOI         : {doi_url}\n")
            f.write(f"OpenAlex Biblio      : {biblio}\n")
            f.write(f"OpenAlex Cited by    : {data.get('cited_by_count', '?')}\n")
            f.write(f"OpenAlex Type        : {data.get('type', '?')}\n")
            ids = data.get("ids", {})
            if ids:
                id_parts = [f"{k}={v}" for k, v in ids.items() if k != "openalex"]
                if id_parts:
                    f.write(f"OpenAlex IDs         : {'; '.join(id_parts)}\n")
            loc = (data.get("primary_location") or {})
            if loc:
                is_oa = loc.get("is_oa", False)
                pdf_url = loc.get("pdf_url") or ""
                landing = loc.get("landing_page_url") or ""
                oa_status = "Open Access" if is_oa else "Closed"
                parts = [f"Status: {oa_status}"]
                if pdf_url:
                    parts.append(f"PDF: {pdf_url}")
                if landing:
                    parts.append(f"Landing: {landing}")
                f.write(f"OpenAlex Access      : {' | '.join(parts)}\n")
        elif error:
            f.write(f"[Error: {error}]\n")
    return fname


# =================== ОСНОВНОЙ ЦИКЛ ===================

def batch_lookup(targets, prefix, timeout, mailto, out_dir=None, crosscheck=True):
    """Пакетный lookup DOI через OpenAlex API.

    crosscheck=True (по умолчанию): сверять fact-строку с метаданными OpenAlex
    и выдавать MISMATCH при расхождении.
    crosscheck=False: только проверка существования DOI (старый режим).
    """
    out_dir = Path(out_dir) if out_dir else default_out_dir()
    results = {}
    doi_count = 0
    skip_count = 0

    for target in targets:
        tid = target["id"]
        url = target["url"]
        fact = target["fact"]
        expect = target.get("expect", "")

        print(f"[{tid}] {url}", flush=True)
        print(f"    fact   : {fact}", flush=True)
        print(f"    expect : {expect}", flush=True)

        doi = extract_doi(target)
        if not doi:
            print(f"    status : SKIP (no DOI found in URL or expect)", flush=True)
            status = "SKIP"
            error = "No DOI to look up"
            data = None
            skip_count += 1
        else:
            doi_count += 1
            print(f"    doi    : {doi}", flush=True)
            start_ts = time.time()
            data, error = lookup_doi(doi, timeout, mailto)
            elapsed = time.time() - start_ts
            if error:
                status = "ERROR"
                print(f"    status : {status} — {error}  elapsed={elapsed:.1f}s", flush=True)
            else:
                title = data.get("title", "?")
                year = data.get("publication_year", "?")
                cited = data.get("cited_by_count", 0)

                # Кросс-проверка: fact vs реальные метаданные (с поддержкой RU↔EN)
                if crosscheck:
                    status, match_detail = classify_fact_match(fact, data)
                    is_match = (status == "CONFIRMED")
                    if status == "MISMATCH":
                        error = f"Fact does not match article metadata: {match_detail}"
                    elif status == "UNCERTAIN":
                        error = f"Uncertain match (manual/lite check recommended): {match_detail}"
                else:
                    is_match = True
                    status = "CONFIRMED"

                print(f"    status : {status}  title=\"{title[:80]}\"  year={year}  cited={cited}  match={is_match}  elapsed={elapsed:.1f}s", flush=True)

        fname = _save_result(target, doi, data, error, status, prefix, out_dir)
        print(f"    saved  : {fname}", flush=True)

        results[tid] = {
            "fact": fact, "url": url, "doi": doi,
            "status": status, "error": error,
        }

        if doi and not error:
            time.sleep(0.15)

    # Summary
    print("\n" + "=" * 70, flush=True)
    print("SUMMARY (OpenAlex Ур.0.5)", flush=True)
    print("=" * 70, flush=True)
    confirmed = sum(1 for r in results.values() if r["status"] == "CONFIRMED")
    uncertain = sum(1 for r in results.values() if r["status"] == "UNCERTAIN")
    mismatches = sum(1 for r in results.values() if r["status"] == "MISMATCH")
    errors = sum(1 for r in results.values() if r["status"] == "ERROR")
    skipped = sum(1 for r in results.values() if r["status"] == "SKIP")
    print(f"CONFIRMED={confirmed}  UNCERTAIN={uncertain}  MISMATCH={mismatches}  ERROR={errors}  SKIP={skipped}  TOTAL={len(results)}", flush=True)
    for tid, r in results.items():
        if r["status"] == "CONFIRMED":
            flag = "OK"
        elif r["status"] == "UNCERTAIN":
            flag = "UNC"
        elif r["status"] == "MISMATCH":
            flag = "MIS"
        elif r["status"] == "ERROR":
            flag = "ERR"
        else:
            flag = "SKIP"
        doi_str = r['doi'] or '—'
        err_str = f"  err={r['error']}" if r.get("error") else ""
        print(f"  [{flag}] {tid}  doi:{doi_str}  {r['url']}{err_str}", flush=True)

    return results


# =================== MAIN ===================

def main():
    ap = argparse.ArgumentParser(description="OpenAlex fact-checker — Ур.0.5 каскада")
    ap.add_argument("--targets", required=True, help="path to JSON with TARGETS list")
    ap.add_argument("--prefix", default="oa", help="output filename prefix (default: oa)")
    ap.add_argument("--timeout", type=int, default=15, help="per-request timeout (s) (default: 15)")
    ap.add_argument("--mailto", default=_DEFAULT_MAILTO,
                    help=f"email for OpenAlex Polite Pool (default: {_DEFAULT_MAILTO})")
    ap.add_argument("--out-dir", default=None,
                    help="output directory (default: <repo>/workspace)")
    ap.add_argument("--no-crosscheck", action="store_true",
                    help="Disable fact-vs-metadata cross-check (all existing DOIs → CONFIRMED)")
    args = ap.parse_args()

    fix_windows_console()
    validate_prefix(args.prefix)

    targets = read_targets(Path(args.targets), validate_url_https=False)
    print(f"Loaded {len(targets)} targets from {args.targets}", flush=True)
    out_dir = Path(args.out_dir) if args.out_dir else default_out_dir()
    print(f"Settings: timeout={args.timeout}s, prefix={args.prefix}, out-dir={out_dir}", flush=True)

    batch_lookup(targets, args.prefix, args.timeout, args.mailto, out_dir,
                 crosscheck=not args.no_crosscheck)


if __name__ == "__main__":
    main()
