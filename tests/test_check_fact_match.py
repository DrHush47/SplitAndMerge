"""Тесты check_fact_match (factcheck_openalex.py, Ур.0.5).

Кейсы построены по реальному коду функции (строки ~104–181):
- читаются ключи data["title"] и data["authorships"][0]["author"]["display_name"];
- проверка 1 — фамилия первого автора (str или кортеж из двух вариантов)
  подстрокой (case-insensitive) в fact;
- проверка 2 — пересечение значимых слов fact (после разделителя) с title:
  стоп-слова и слова <4 символов исключаются; при 3+ словах порог 30%,
  при 1–2 словах — любое совпадение;
- разделители fact проверяются в порядке [" — ", ". ", " —", "— "];
- is_match = есть хотя бы один пройденный чек.
"""

import pytest

from pipeline.openalex.factcheck_openalex import (
    check_fact_match,
    classify_fact_match,
    get_first_author_surname,
)


def oa_data(title="", authors=()):
    """Словарь метаданных ровно по тем ключам, что читает check_fact_match."""
    return {
        "title": title,
        "authorships": [{"author": {"display_name": name}} for name in authors],
    }


# (fact, title, authors, ожидаемый is_match, подстроки detail)
CASES = [
    # --- оба чека прошли ---
    (
        "Topol E.J. — High-performance medicine: the convergence of human and artificial intelligence",
        "High-performance medicine: the convergence of human and artificial intelligence",
        ("Eric Topol",),
        True,
        ["author 'Topol' found in fact", "title overlap"],
    ),
    # --- прошёл только чек автора ---
    (
        "Smith J. — Some totally different article about widgets and gears and cogs",
        "completely unrelated topic words",
        ("John Smith",),
        True,
        ["author 'Smith' found in fact", "title overlap only"],
    ),
    # --- прошёл только чек заголовка ---
    (
        "The paper about neural networks and deep learning systems",
        "neural networks and deep learning systems",
        ("Zhang Wei",),
        True,
        ["authors ['Wei', 'Zhang'] NOT in fact", "title overlap"],
    ),
    # --- ни один чек не прошёл (MISMATCH) ---
    (
        "Unrelated paper about quantum computing bits",
        "completely different subject matter",
        ("Maria Garcia",),
        False,
        ["authors ['Garcia', 'Maria'] NOT in fact", "title overlap only"],
    ),
    # --- фамилия-строка (имя из одного слова) ---
    (
        "Topol E.J. — Quantum computing advances",
        "completely different subject matter",
        ("Topol",),
        True,
        ["author 'Topol' found in fact"],
    ),
    # --- кортеж фамилий: западный вариант ---
    (
        "Zhang W. — Something unrelated here",
        "completely different subject matter",
        ("Wei Zhang",),
        True,
        ["author 'Zhang' found in fact"],
    ),
    # --- кортеж фамилий: восточный вариант ---
    (
        "Wei Z. — Something unrelated here",
        "completely different subject matter",
        ("Wei Zhang",),
        True,
        ["author 'Wei' found in fact"],
    ),
    # --- разделитель ". " ---
    (
        "Smith J. Article title words here",
        "article title words here",
        ("John Smith",),
        True,
        ["title overlap"],
    ),
    # --- разделитель " —" (пробел + тире) ---
    (
        "Smith J —Title words here",
        "title words here",
        ("John Smith",),
        True,
        ["title overlap"],
    ),
    # --- разделитель "— " (тире + пробел) ---
    (
        "Smith J— Title words here",
        "title words here",
        ("John Smith",),
        True,
        ["title overlap"],
    ),
    # --- только стоп-слова в заголовочной части → fact_words пусто ---
    (
        "Smith J. To be or not to be",
        "unrelated totally",
        ("John Smith",),
        True,
        ["author 'Smith' found in fact"],
    ),
    # --- слова короче 4 символов исключаются ---
    (
        "Smith J. A cat and a dog",
        "unrelated words",
        ("John Smith",),
        True,
        ["author 'Smith' found in fact"],
    ),
    # --- порог 30% при 3+ словах: совпадение засчитано (75%) ---
    (
        "Doe J. Alpha beta gamma delta",
        "alpha beta gamma epsilon",
        ("John Doe",),
        True,
        ["title overlap 75%"],
    ),
    # --- порог 30% при 3+ словах: ниже порога (25%) ---
    (
        "Doe J. Alpha beta gamma delta",
        "alpha unrelated words here",
        ("John Doe",),
        True,
        ["title overlap only 25%"],
    ),
    # --- случай 1–2 слов: совпадение есть ---
    (
        "Doe J. Quantum birds",
        "quantum birds",
        ("John Doe",),
        True,
        ["title words match"],
    ),
    # --- случай 1–2 слов: совпадения нет ---
    (
        "Doe J. Quantum birds",
        "unrelated topics",
        ("John Doe",),
        True,
        ["no title word overlap"],
    ),
    # --- пустой title: чек заголовка не может пройти ---
    (
        "Smith J. — Quantum computing advances",
        "",
        ("John Smith",),
        True,
        ["author 'Smith' found in fact"],
    ),
    # --- пустые авторы: чек автора пропускается, работает только заголовок ---
    (
        "Some fact about quantum computing advances",
        "quantum computing advances",
        (),
        True,
        ["title overlap"],
    ),
    # --- пустой fact: оба чека не проходят ---
    (
        "",
        "quantum computing advances",
        ("John Smith",),
        False,
        ["authors ['Smith', 'John'] NOT in fact"],
    ),
    # --- регистр: фамилия в fact в другом регистре ---
    (
        "TOPOL E.J. — Quantum computing advances",
        "completely different subject matter",
        ("Eric Topol",),
        True,
        ["author 'Topol' found in fact"],
    ),
    # --- регрессия: двоеточие в title нормализуется ---
    (
        "Doe J. High performance medicine",
        "High performance medicine:",
        ("Jane Doe",),
        True,
        ["title overlap 100%"],
    ),
    # --- регрессия: пунктуационный мусор title не ломает overlap ---
    (
        "Doe J. Alpha beta gamma",
        "!!! alpha, beta; gamma...",
        ("Jane Doe",),
        True,
        ["title overlap 100%"],
    ),
    # --- регрессия: пустые токены после strip игнорируются ---
    (
        "Doe J. Alpha beta gamma",
        "... alpha ... beta ... gamma ...",
        ("Jane Doe",),
        True,
        ["title overlap 100%"],
    ),
]


@pytest.mark.parametrize("fact,title,authors,expected,detail_parts", CASES)
def test_check_fact_match(fact, title, authors, expected, detail_parts):
    is_match, detail = check_fact_match(fact, oa_data(title=title, authors=authors))
    assert is_match is expected
    for part in detail_parts:
        assert part in detail, f"detail должен содержать {part!r}, получено: {detail!r}"


# --- прямые проверки get_first_author_surname ---

def test_surname_str_for_single_word_name():
    assert get_first_author_surname(oa_data(authors=("Topol",))) == "Topol"


def test_surname_tuple_for_multiword_name():
    assert get_first_author_surname(oa_data(authors=("Wei Zhang",))) == ("Zhang", "Wei")


def test_surname_empty_without_authors():
    assert get_first_author_surname(oa_data(authors=())) == ""


def test_surname_empty_without_display_name():
    data = {"title": "x", "authorships": [{"author": {}}]}
    assert get_first_author_surname(data) == ""


# --- двуязычные проверки RU ↔ EN (перенесённые из Ур.0.7 BioMed) ---

def test_cyrillic_author_translit_confirmed():
    """Кириллическая цитата российской статьи (OpenAlex отдаёт EN-название и лат. авторов)."""
    data = oa_data(
        title="Quantitative determination of monoamine neurotransmitters in rat brain homogenates using HPLC-MS/MS",
        authors=("Nikita S. Popov", "S. A. Donskov"),
    )
    fact = "Попов Н.С., Донсков С.А. Количественное определение моноаминовых нейротрансмиттеров в мозге крыс"
    status, detail = classify_fact_match(fact, data)
    assert status == "CONFIRMED"
    assert "author 'Popov' found in fact (translit)" in detail
    is_match, _ = check_fact_match(fact, data)
    assert is_match is True


def test_cyrillic_coauthor_translit_confirmed():
    """Если фамилия первого автора транслитерирована нестандартно, соавтор всё равно подтверждает."""
    data = oa_data(
        title="Cytopathological characteristics for provoked lesions of squamous epithelia of digestive system",
        authors=("Valeria Schestakova", "S. A. Donskov"),
    )
    fact = "Шестакова В.Г., Донсков С.А. Морфологическая характеристика эпителия пищеварительного тракта"
    status, detail = classify_fact_match(fact, data)
    assert status == "CONFIRMED"
    assert "co-author 'Donskov' found in fact (translit)" in detail


def test_cyrillic_cognates_title_match_confirmed():
    """Даже при отсутствии автора совпадение медицинских корней подтверждает статью."""
    data = oa_data(
        title="Morphological changes in periodontal tissues under reprogramming macrophages",
        authors=("V. Rumiantsev",),
    )
    fact = "Морфологические изменения в тканях пародонта при репрограммировании макрофагов"
    status, detail = classify_fact_match(fact, data)
    assert status == "CONFIRMED"
    assert "title overlap" in detail


def test_cyrillic_language_barrier_returns_uncertain_not_mismatch():
    """При языковом барьере без совпадения фамилий/корней — UNCERTAIN, а не ложный MISMATCH."""
    data = oa_data(
        title="Novel randomized double-blind evaluation of therapeutic efficacy",
        authors=("A. Schetina",),
    )
    fact = "Щетина Р.Г. — Новая оценка эффективности применения подхода"
    status, detail = classify_fact_match(fact, data)
    assert status == "UNCERTAIN"
    assert "language barrier" in detail
    is_match, _ = check_fact_match(fact, data)
    assert is_match is False


def test_latin_unrelated_still_returns_mismatch():
    """В одном алфавите (EN vs EN) при расхождении по-прежнему жёсткий MISMATCH."""
    data = oa_data(
        title="Deep learning for pediatric chest radiographs",
        authors=("Eric Topol",),
    )
    fact = "Smith J. — Quantum dots in semiconductor physics"
    status, _ = classify_fact_match(fact, data)
    assert status == "MISMATCH"
