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
                    "pmcid": "",
                    "title": entry.get("title", ""),
                    "authors": authors,
                    "first_author": authors[0] if authors else "",
                    "journal": entry.get("source", ""),
                    "pubdate": entry.get("pubdate", ""),
                    "volume": entry.get("volume", ""),
                    "issue": entry.get("issue", ""),
                    "pages": entry.get("pages", ""),
                    "doi": "",
                    "source_api": "NCBI E-utilities"
                }
                # Извлечение DOI и PMCID из списка articleids в ответе NCBI
                articleids = entry.get("articleids", [])
                if isinstance(articleids, list):
                    for aid in articleids:
                        if isinstance(aid, dict):
                            idtype = aid.get("idtype", "").lower()
                            if idtype == "doi":
                                norm["doi"] = aid.get("value", "")
                            elif idtype in ("pmc", "pmcid"):
                                val = aid.get("value", "")
                                m_pmc = re.search(r"(PMC\d+)", val, re.IGNORECASE)
                                if m_pmc:
                                    norm["pmcid"] = m_pmc.group(1).upper()
                                else:
                                    norm["pmcid"] = val if val.upper().startswith("PMC") else f"PMC{val}"
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


# =================== ТРАНСЛИТЕРАЦИЯ И БИОМЕДИЦИНСКИЕ ТЕРМИНЫ ===================

CYRILLIC_TO_LATIN = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
}


def transliterate_cyrillic(text: str) -> str:
    """Транслитерация кириллицы в латиницу для сопоставления фамилий и терминов."""
    return "".join(CYRILLIC_TO_LATIN.get(ch, ch) for ch in text.lower())


def has_cyrillic(text: str) -> bool:
    """Проверка наличия символов кириллицы в строке."""
    return bool(re.search(r'[\u0400-\u04FF]', text))


# Двуязычный словарь медицинских и гистологических корней (RU -> EN stem)
BIOMED_COGNATES = {
    # Органы, ткани, клетки
    "миокард": "myocard",
    "кардио": "cardio",
    "кардиолог": "cardiolog",
    "сердеч": "cardiac",
    "сердц": "heart",
    "сосуд": "vascul",
    "артери": "arter",
    "вен": "vein",
    "эндотели": "endothel",
    "печен": "hepat",
    "печеноч": "hepat",
    "почеч": "renal",
    "почек": "renal",
    "почк": "kidney",
    "легк": "pulmon",
    "легоч": "pulmon",
    "мозг": "cerebr",
    "мозгов": "cerebr",
    "ткань": "tissue",
    "тканей": "tissue",
    "ткани": "tissue",
    "клетк": "cell",
    "клеточ": "cell",
    "кров": "blood",
    "сыворотк": "serum",
    "плазм": "plasma",
    # Патологические и морфологические процессы
    "гипертроф": "hypertroph",
    "морфолог": "morpholog",
    "морфометр": "morphometr",
    "гистолог": "histolog",
    "онколог": "oncolog",
    "опухол": "tumor",
    "рак": "cancer",
    "карцином": "carcinom",
    "диабет": "diabet",
    "атеросклероз": "atheroscler",
    "ишеми": "ischem",
    "инфаркт": "infarct",
    "некроз": "necro",
    "фиброз": "fibros",
    "склероз": "scleros",
    "воспален": "inflammat",
    "апоптоз": "apoptos",
    "пролифераци": "proliferat",
    "мутаци": "mutat",
    "гипертензи": "hypertens",
    # Молекулярная биология, биохимия, генетика
    "экспресси": "express",
    "ген": "gene",
    "геном": "genom",
    "генети": "genet",
    "хромосом": "chromosom",
    "белок": "protein",
    "белк": "protein",
    "рецептор": "receptor",
    "ингибитор": "inhibitor",
    "активатор": "activator",
    "фермент": "enzym",
    "маркер": "marker",
    "биомаркер": "biomarker",
    "молекуляр": "molecular",
    "структур": "structur",
    "регуляци": "regulat",
    "функци": "function",
    "активност": "activ",
    # Клиника и терапия
    "терапи": "therap",
    "клинич": "clinic",
    "фармакол": "pharmacol",
    "биопси": "biops",
    "синдром": "syndrom",
    "патолог": "patholog",
    "анатом": "anatom",
    "иммун": "immun",
    "пациент": "patient",
    "стади": "stage",
    "диагностик": "diagnos",
    "трансплант": "transplant",
    "препарат": "drug",
    "лекарств": "medicat",
}


# =================== КРОСС-ПРОВЕРКА FACT vs METADATA ===================

def check_biomed_fact_match(fact, data):
    """Сравнить fact-строку с биомедицинскими метаданными (автор, ключевые слова названия).

    Возвращает (verdict, detail), где:
      - verdict: "CONFIRMED" | "MISMATCH" | "UNCERTAIN"
      - detail: текстовое описание совпавших и несовпавших признаков

    Принципы Evidence-First:
      - Одно лишь совпадение фамилии автора при 0% совпадении темы статьи бракуется как MISMATCH
        (FP-киллер против цитирования чужой статьи известного автора или галлюцинаций LLM).
      - Кириллические факты транслитерируются для поиска авторов и проверяются по словарю
        биологических и медицинских корней. Если программно подтвердить русский факт
        против англоязычной статьи невозможно, возвращается UNCERTAIN (эскалация Рецензенту),
        а не ложный MISMATCH.
    """
    title = (data.get("title") or "").lower()
    first_author = data.get("first_author", "")
    authors = data.get("authors", [])
    fact_lower = fact.lower()
    fact_translit = transliterate_cyrillic(fact_lower)
    is_cyrillic = has_cyrillic(fact)

    checks_passed = []
    checks_failed = []

    # 1. Проверка фамилии автора (с поддержкой транслитерации и списка соавторов)
    author_hit = False
    matched_author = ""
    author_surname = first_author.split()[0].strip(".,") if first_author else ""

    if author_surname and len(author_surname) >= 2:
        sn_lower = author_surname.lower()
        if sn_lower in fact_lower or sn_lower in fact_translit:
            author_hit = True
            matched_author = author_surname
            checks_passed.append(f"first author '{author_surname}' found in fact")

    if not author_hit and authors:
        for a in authors:
            sn = a.split()[0].strip(".,") if a.split() else ""
            if len(sn) >= 3:
                sn_lower = sn.lower()
                if sn_lower in fact_lower or sn_lower in fact_translit:
                    author_hit = True
                    matched_author = sn
                    checks_passed.append(f"co-author '{sn}' found in fact")
                    break

    if not author_hit and author_surname:
        checks_failed.append(f"author '{author_surname}' NOT in fact")

    # 2. Выделение содержательной части факт-строки
    fact_title_part = fact_lower
    for sep in [" — ", ". ", " —", "— ", ": "]:
        if sep in fact_lower:
            fact_title_part = fact_lower.split(sep, 1)[1]
            break

    fact_words = [
        w.strip(".,;:()[]«»\"'/-") for w in fact_title_part.split()
    ]
    fact_words = [
        w for w in fact_words
        if len(w) >= 4 and w not in STOP_WORDS
    ]

    title_words = {
        w.strip(".,;:()[]«»\"'/-") for w in title.split()
    }
    title_words = {w for w in title_words if len(w) >= 4 and w not in STOP_WORDS}

    # 3. Сопоставление слов названия (прямое, через корни и транслитерацию)
    matched_fact_words = set()
    for fw in fact_words:
        # Прямое совпадение
        if fw in title_words or fw in title:
            matched_fact_words.add(fw)
            continue
        # Проверка медицинских и гистологических корней
        for ru_stem, en_stem in BIOMED_COGNATES.items():
            if ru_stem in fw:
                if any(en_stem in tw for tw in title_words) or en_stem in title:
                    matched_fact_words.add(fw)
                    break
        # Проверка транслитерированного корня
        fw_translit = transliterate_cyrillic(fw)
        if len(fw_translit) >= 5:
            prefix5 = fw_translit[:5]
            if any(prefix5 in tw for tw in title_words):
                matched_fact_words.add(fw)

    overlap = len(matched_fact_words) / len(fact_words) if fact_words else 0.0
    matches_count = len(matched_fact_words)

    if len(fact_words) >= 3:
        if overlap >= 0.25:
            checks_passed.append(f"title overlap {overlap:.0%} ({matches_count}/{len(fact_words)} words)")
        else:
            checks_failed.append(f"title overlap only {overlap:.0%} ({matches_count}/{len(fact_words)} words)")
    elif len(fact_words) >= 1:
        if matches_count >= 1:
            checks_passed.append(f"title words match: {matched_fact_words}")
        else:
            checks_failed.append("no title word overlap")

    detail = "; ".join(checks_passed + checks_failed)

    # 4. Решение: Evidence-First классификация вердикта
    # Сценарий A: Высокое совпадение названия (>= 25% при >= 3 словах, или >= 2 слов)
    if (len(fact_words) >= 3 and overlap >= 0.25) or matches_count >= 2:
        return "CONFIRMED", detail

    # Сценарий B: Одно совпавшее слово при коротком названии (<= 4 слов)
    if matches_count >= 1 and len(fact_words) <= 4:
        if author_hit:
            return "CONFIRMED", detail
        elif not is_cyrillic and overlap >= 0.30:
            return "CONFIRMED", detail

    # Сценарий C: Автор совпал, но перекрытие названия 0% (при наличии проверяемых слов)
    if author_hit and matches_count == 0 and len(fact_words) >= 1:
        if is_cyrillic:
            # Для кириллического факта: автор распознан, но русские слова могут быть вне словаря корней
            return "UNCERTAIN", f"author '{matched_author}' found, but title is Cyrillic without known cognates; {detail}"
        else:
            # Для латинского факта: тот же автор, но название не совпадает ни на одно слово -> явный MISMATCH (FP-киллер)
            return "MISMATCH", f"FP-killer: author '{matched_author}' found, but 0% title overlap; {detail}"

    # Сценарий D: Автор совпал и в факте не было проверяемых слов названия
    if author_hit and len(fact_words) == 0:
        return "CONFIRMED", detail

    # Сценарий E: Ни автор, ни название не подтвердились
    if is_cyrillic:
        # Языковой барьер RU -> EN: статья существует в PubMed, но автоматический анализ не дал подтверждения
        return "UNCERTAIN", f"Cyrillic fact vs English metadata: cannot verify automatically ({detail})"

    return "MISMATCH", detail


# =================== СОХРАНЕНИЕ РЕЗУЛЬТАТА ===================

def save_biomed_result(target, id_val, id_type, data, error, status, prefix, out_dir):
    """Сохранить артефакт workspace/{prefix}_{clean_id}.txt."""
    out_dir.mkdir(parents=True, exist_ok=True)
    clean_id = re.sub(r"[^\w.-]", "_", str(target.get("id", "target"))).strip(".")
    if not clean_id:
        clean_id = "target"
    out_file = out_dir / f"{prefix}_{clean_id}.txt"

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
                verdict, detail = check_biomed_fact_match(t.get("fact", ""), data)
                if verdict == "CONFIRMED":
                    status = "CONFIRMED"
                elif verdict == "UNCERTAIN":
                    status = "UNCERTAIN"
                    error = f"Crosscheck uncertain: {detail}"
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
    uncertain = sum(1 for r in results.values() if r["status"] == "UNCERTAIN")
    errors = sum(1 for r in results.values() if r["status"] == "ERROR")
    skipped = sum(1 for r in results.values() if r["status"] == "SKIP")

    print("\n" + "=" * 60)
    print(f"SUMMARY (biomed): CONFIRMED={confirmed}  MISMATCH={mismatch}  UNCERTAIN={uncertain}  ERROR={errors}  SKIP={skipped}")
    print("=" * 60)

    # Код выхода: 1 при наличии MISMATCH, UNCERTAIN или ERROR (требуется разбор / эскалация)
    needs_review = (mismatch > 0 or errors > 0 or uncertain > 0)
    sys.exit(1 if needs_review else 0)


if __name__ == "__main__":
    main()
