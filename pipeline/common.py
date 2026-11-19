#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
common.py — Shared utilities for factcheck pipeline scripts.

Used by:
  - factcheck_crawl4ai.py  (Ур.2)
  - factcheck_openalex.py  (Ур.0.5)
  - factcheck_scrapling.py (Ур.3)

Eliminates code duplication of: PREFIX_PATTERN, PREFIX_FORBIDDEN,
_read_targets, _validate_prefix, and the Windows Unicode console fix.
"""

import io
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Prefix validation constants
# ---------------------------------------------------------------------------

PREFIX_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
PREFIX_FORBIDDEN = {".", ".."}  # only . and .. parent-relative; ... and beyond are just filenames


# ---------------------------------------------------------------------------
# Windows Unicode console fix
# ---------------------------------------------------------------------------

def fix_windows_console():
    """Fix Unicode output on Windows: replace unencodable chars instead of crashing."""
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


# ---------------------------------------------------------------------------
# targets.json parsing
# ---------------------------------------------------------------------------

def read_targets(path, validate_url_https=True):
    """Read and validate a targets.json file.

    Args:
        path: Path to the targets JSON file.
        validate_url_https: If True, require url to start with http:// or https://.
                            Set False for OpenAlex (DOI-based targets may omit the
                            http prefix — e.g. a bare DOI as the url field).

    Returns:
        list of target dicts.

    Exits with code 2 on validation failure.
    """
    raw = path.read_text(encoding="utf-8-sig")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"FATAL: invalid JSON in {path}: {exc}", file=sys.stderr)
        sys.exit(2)
    if not isinstance(data, list):
        print("FATAL: targets JSON must be a list at top level", file=sys.stderr)
        sys.exit(2)
    required = {"id", "fact", "url"}
    for i, t in enumerate(data):
        missing = required - set(t.keys())
        if missing:
            print(f"FATAL: target #{i} missing fields: {missing}", file=sys.stderr)
            sys.exit(2)
        if validate_url_https:
            if not isinstance(t["url"], str) or not t["url"].startswith(("http://", "https://")):
                print(f"FATAL: target #{i} url must start with http:// or https://, got: {t['url']!r}",
                      file=sys.stderr)
                sys.exit(2)
    return data


# ---------------------------------------------------------------------------
# Output directory
# ---------------------------------------------------------------------------

def default_out_dir():
    """Каталог рантайм-артефактов: <корень репо>/workspace (вне git)."""
    return Path(__file__).resolve().parents[1] / "workspace"


# ---------------------------------------------------------------------------
# Prefix validation
# ---------------------------------------------------------------------------

def validate_prefix(prefix: str):
    """Validate --prefix argument value. Exits with code 2 on unsafe values."""
    if prefix in PREFIX_FORBIDDEN:
        print(f"FATAL: --prefix '{prefix}' is reserved/unsafe", file=sys.stderr)
        sys.exit(2)
    if "/" in prefix or "\\" in prefix:
        print(f"FATAL: --prefix must not contain path separator, got: {prefix!r}", file=sys.stderr)
        sys.exit(2)
    if not PREFIX_PATTERN.match(prefix):
        print(f"FATAL: --prefix must match [A-Za-z0-9_.-]+, got: {prefix!r}", file=sys.stderr)
        sys.exit(2)


# ---------------------------------------------------------------------------
# Stop-words — общий словарь для term-анализа (check_fact_match в openalex,
# significant_terms в manual scanner). Единый источник — импортировать отсюда.
# ---------------------------------------------------------------------------

STOP_WORDS = {
    "the", "a", "an", "of", "in", "on", "to", "for", "and", "or",
    "is", "are", "was", "were", "with", "from", "by", "at", "as",
    "its", "it", "not", "no", "be", "has", "have", "had", "this",
    "that", "which", "their", "been", "can", "may", "will", "would",
    "et", "al", "de", "la", "le", "du", "des",
}


# ---------------------------------------------------------------------------
# Двуязычная поддержка RU ↔ EN (общий SSOT для OpenAlex Ур.0.5 и BioMed Ур.0.7)
# ---------------------------------------------------------------------------

CYRILLIC_TO_LATIN = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
}


def transliterate_cyrillic(text: str) -> str:
    """Транслитерация кириллицы в латиницу для сопоставления фамилий и терминов."""
    return "".join(CYRILLIC_TO_LATIN.get(ch, ch) for ch in text.lower())


def has_cyrillic(text: str) -> bool:
    """True, если строка содержит хотя бы один символ кириллицы."""
    return bool(re.search(r'[\u0400-\u04FF]', text))


def has_word_token(token: str, text: str) -> bool:
    """Проверка вхождения слова/фамилии как целого токена (границы букв, не подстрока).

    Исключает ложные срабатывания вроде 'lin' внутри 'klinicheskie' или 'smith' внутри 'smithson'.
    """
    tok = token.strip().lower()
    if not tok:
        return False
    return bool(re.search(rf"(?<![^\W\d_]){re.escape(tok)}(?![^\W\d_])", text.lower()))


# Точные словарные пары для коротких/омонимичных медицинских терминов,
# где префиксное или подстрочное совпадение давало бы ложные срабатывания
# (напр., «ген» в «агент/рентген/патоген», «рак» в «характер/практика/тракт», «вен» в «проведение»).
EXACT_BIOMED_COGNATES = (
    (
        frozenset({"ген", "гена", "гены", "генов", "генам", "генах", "геном", "генами"}),
        frozenset({"gene", "genes"}),
    ),
    (
        frozenset({"рак", "рака", "раке", "раком", "раковый", "раковая", "раковое", "раковые", "раковых"}),
        frozenset({"cancer", "cancers", "cancerous"}),
    ),
    (
        frozenset({"вен", "вена", "вены", "вене", "веной", "венах", "венам", "венозный", "венозная", "венозных", "венозного"}),
        frozenset({"vein", "veins", "venous"}),
    ),
    (
        frozenset({"ткань", "ткани", "тканей", "тканях", "тканям", "тканью", "тканевой", "тканевых", "тканевого"}),
        frozenset({"tissue", "tissues"}),
    ),
)


# Двуязычный словарь медицинских, гистологических и научных префиксов (RU prefix -> EN prefix | tuple[EN prefix, ...]).
# Матчится строго по началу слова (startswith) с обеих сторон, без поиска внутри случайных подстрок.
BIOMED_COGNATES = {
    # Органы, ткани, клетки
    "миокард": "myocard",
    "кардио": "cardio",
    "кардиолог": "cardiolog",
    "сердеч": ("cardiac", "heart"),
    "сердц": ("heart", "cardiac"),
    "сосуд": "vascul",
    "артери": "arter",
    "венозн": "venous",
    "эндотели": "endothel",
    "эпители": "epithel",
    "пародонт": "periodont",
    "пищеварит": "digestiv",
    "печен": "hepat",
    "почеч": ("renal", "kidney"),
    "почек": ("renal", "kidney"),
    "почк": ("kidney", "renal"),
    "легк": ("pulmon", "lung"),
    "легоч": ("pulmon", "lung"),
    "мозг": ("cerebr", "brain"),
    "мозгов": ("cerebr", "brain"),
    "клетк": "cell",
    "клеточ": "cell",
    "макрофаг": "macrophag",
    "кров": "blood",
    "сыворотк": "serum",
    "плазм": "plasma",
    # Патологические и морфологические процессы
    "гипертроф": "hypertroph",
    "морфолог": "morpholog",
    "морфометр": "morphometr",
    "гистолог": "histolog",
    "эмбриолог": "embryolog",
    "цитолог": "cytolog",
    "онколог": "oncolog",
    "канцероген": "carcinogen",
    "опухол": "tumor",
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
    # Молекулярная биология, биохимия, аналитика, генетика
    "экспресси": "express",
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
    "нейротрансмиттер": "neurotransmitter",
    "хроматограф": "chromatograph",
    "количествен": "quantitativ",
    "микропрепарат": "micropreparat",
    "микроскоп": "microscop",
    "моделирован": "model",
    "фетальн": "fetal",
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


def match_cognate_word(ru_word: str, title_words: set) -> bool:
    """Проверить, соотносится ли русское слово с одним из англоязычных слов заголовка.

    Правила против ложных срабатываний:
      1. Короткие омонимичные термины (ген/рак/вен/ткань) — только по точным формам.
      2. Словарные медицинские корни — только по началу слова (startswith) с обеих сторон.
      3. Транслитерация международных терминов — только по 6+ символьному префиксу с начала слова.
    """
    fw = ru_word.lower()
    if not fw or not title_words:
        return False

    for ru_forms, en_forms in EXACT_BIOMED_COGNATES:
        if fw in ru_forms and (title_words & en_forms):
            return True

    for ru_stem, en_stems in BIOMED_COGNATES.items():
        if fw.startswith(ru_stem):
            targets = (en_stems,) if isinstance(en_stems, str) else en_stems
            if any(tw.startswith(es) for tw in title_words for es in targets):
                return True

    fw_tr = transliterate_cyrillic(fw)
    if len(fw_tr) >= 6:
        prefix6 = fw_tr[:6]
        if any(len(tw) >= 6 and tw.startswith(prefix6) for tw in title_words):
            return True

    return False
