"""Тесты classify_fact_match / check_fact_match (factcheck_openalex.py, Ур.0.5).

Контракт функции:
- читаются ключи data["title"] и data["authorships"][...]["author"]["display_name"];
- проверка 1 — фамилия автора проверяется по границам токенов (case-insensitive);
- проверка 2 — пересечение значимых слов fact (после разделителя) с title:
  стоп-слова и слова <4 символов исключаются; при 3+ словах порог 30%,
  при 1–2 словах в одном алфавите — любое совпадение;
- разделители fact проверяются в порядке [" — ", ". ", " —", "— "];
- CONFIRMED требует подтверждения темы (сильное совпадение заголовка, либо автор + совпадение темы);
  совпадение одного только автора без совпадения темы даёт UNCERTAIN (не CONFIRMED и не MISMATCH).
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


# (fact, title, authors, ожидаемый status, подстроки detail)
CASES = [
    # --- оба чека прошли → CONFIRMED ---
    (
        "Topol E.J. — High-performance medicine: the convergence of human and artificial intelligence",
        "High-performance medicine: the convergence of human and artificial intelligence",
        ("Eric Topol",),
        "CONFIRMED",
        ["author 'Topol' found in fact", "title overlap"],
    ),
    # --- совпал только автор без темы → UNCERTAIN (не CONFIRMED и не MISMATCH) ---
    (
        "Smith J. — Some totally different article about widgets and gears and cogs",
        "completely unrelated topic words",
        ("John Smith",),
        "UNCERTAIN",
        ["author-only match without title confirmation", "author 'Smith' found in fact", "title overlap only"],
    ),
    # --- прошёл только чек заголовка → CONFIRMED ---
    (
        "The paper about neural networks and deep learning systems",
        "neural networks and deep learning systems",
        ("Zhang Wei",),
        "CONFIRMED",
        ["authors ['Wei', 'Zhang'] NOT in fact", "title overlap"],
    ),
    # --- ни один чек не прошёл → MISMATCH ---
    (
        "Unrelated paper about quantum computing bits",
        "completely different subject matter",
        ("Maria Garcia",),
        "MISMATCH",
        ["authors ['Garcia', 'Maria'] NOT in fact", "title overlap only"],
    ),
    # --- фамилия-строка (имя из одного слова) + тема → CONFIRMED ---
    (
        "Topol E.J. — Quantum computing advances",
        "quantum computing advances in medicine",
        ("Topol",),
        "CONFIRMED",
        ["author 'Topol' found in fact", "title overlap"],
    ),
    # --- кортеж фамилий: западный вариант (без темы → UNCERTAIN, фамилия найдена) ---
    (
        "Zhang W. — Something unrelated here",
        "completely different subject matter",
        ("Wei Zhang",),
        "UNCERTAIN",
        ["author 'Zhang' found in fact"],
    ),
    # --- кортеж фамилий: восточный вариант (без темы → UNCERTAIN, фамилия найдена) ---
    (
        "Wei Z. — Something unrelated here",
        "completely different subject matter",
        ("Wei Zhang",),
        "UNCERTAIN",
        ["author 'Wei' found in fact"],
    ),
    # --- разделитель ". " ---
    (
        "Smith J. Article title words here",
        "article title words here",
        ("John Smith",),
        "CONFIRMED",
        ["title overlap"],
    ),
    # --- разделитель " —" (пробел + тире) ---
    (
        "Smith J —Title words here",
        "title words here",
        ("John Smith",),
        "CONFIRMED",
        ["title overlap"],
    ),
    # --- разделитель "— " (тире + пробел) ---
    (
        "Smith J— Title words here",
        "title words here",
        ("John Smith",),
        "CONFIRMED",
        ["title overlap"],
    ),
    # --- только стоп-слова в заголовочной части → fact_words пусто, только автор → UNCERTAIN ---
    (
        "Smith J. To be or not to be",
        "unrelated totally",
        ("John Smith",),
        "UNCERTAIN",
        ["author 'Smith' found in fact"],
    ),
    # --- слова короче 4 символов исключаются → только автор → UNCERTAIN ---
    (
        "Smith J. A cat and a dog",
        "unrelated words",
        ("John Smith",),
        "UNCERTAIN",
        ["author 'Smith' found in fact"],
    ),
    # --- порог 30% при 3+ словах: совпадение засчитано (75%) ---
    (
        "Doe J. Alpha beta gamma delta",
        "alpha beta gamma epsilon",
        ("John Doe",),
        "CONFIRMED",
        ["title overlap 75%"],
    ),
    # --- автор + 1 слово заголовка (25% < 30%, но тема частично подтверждена вместе с автором) → CONFIRMED ---
    (
        "Doe J. Alpha beta gamma delta",
        "alpha unrelated words here",
        ("John Doe",),
        "CONFIRMED",
        ["author 'Doe' found in fact", "title overlap only 25%"],
    ),
    # --- случай 1–2 слов: совпадение есть ---
    (
        "Doe J. Quantum birds",
        "quantum birds",
        ("John Doe",),
        "CONFIRMED",
        ["title words match"],
    ),
    # --- случай 1–2 слов: совпадения нет (один автор → UNCERTAIN) ---
    (
        "Doe J. Quantum birds",
        "unrelated topics",
        ("John Doe",),
        "UNCERTAIN",
        ["author 'Doe' found in fact", "no title word overlap"],
    ),
    # --- пустой title: чек заголовка не может пройти (один автор → UNCERTAIN) ---
    (
        "Smith J. — Quantum computing advances",
        "",
        ("John Smith",),
        "UNCERTAIN",
        ["author 'Smith' found in fact"],
    ),
    # --- пустые авторы: чек автора пропускается, работает только заголовок ---
    (
        "Some fact about quantum computing advances",
        "quantum computing advances",
        (),
        "CONFIRMED",
        ["title overlap"],
    ),
    # --- пустой fact: оба чека не проходят → MISMATCH ---
    (
        "",
        "quantum computing advances",
        ("John Smith",),
        "MISMATCH",
        ["authors ['Smith', 'John'] NOT in fact"],
    ),
    # --- регистр: фамилия в fact в другом регистре + тема → CONFIRMED ---
    (
        "TOPOL E.J. — Quantum computing advances",
        "quantum computing advances",
        ("Eric Topol",),
        "CONFIRMED",
        ["author 'Topol' found in fact", "title overlap"],
    ),
    # --- регрессия: двоеточие в title нормализуется ---
    (
        "Doe J. High performance medicine",
        "High performance medicine:",
        ("Jane Doe",),
        "CONFIRMED",
        ["title overlap 100%"],
    ),
    # --- регрессия: пунктуационный мусор title не ломает overlap ---
    (
        "Doe J. Alpha beta gamma",
        "!!! alpha, beta; gamma...",
        ("Jane Doe",),
        "CONFIRMED",
        ["title overlap 100%"],
    ),
    # --- регрессия: пустые токены после strip игнорируются ---
    (
        "Doe J. Alpha beta gamma",
        "... alpha ... beta ... gamma ...",
        ("Jane Doe",),
        "CONFIRMED",
        ["title overlap 100%"],
    ),
]


@pytest.mark.parametrize("fact,title,authors,expected_status,detail_parts", CASES)
def test_check_fact_match(fact, title, authors, expected_status, detail_parts):
    data = oa_data(title=title, authors=authors)
    status, detail = classify_fact_match(fact, data)
    assert status == expected_status
    is_match, _ = check_fact_match(fact, data)
    assert is_match is (expected_status == "CONFIRMED")
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


# --- негативные тесты против ложных CONFIRMED (ревью эвристик) ---

def test_given_name_does_not_confirm_author():
    """Личное имя (parts[0]) первого автора или соавтора не засчитывается как фамилия."""
    data = oa_data(
        title="Synthesis of organic catalysts",
        authors=("Elena Sokolova", "Valeria Morozova"),
    )
    fact_first = "Елена Петрова — Исследование свойств полимеров"
    status1, detail1 = classify_fact_match(fact_first, data)
    assert status1 == "UNCERTAIN"
    assert "found in fact" not in detail1

    fact_co = "Валерия Иванова — Исследование свойств полимеров"
    status2, detail2 = classify_fact_match(fact_co, data)
    assert status2 == "UNCERTAIN"
    assert "found in fact" not in detail2


def test_surname_substring_inside_word_does_not_match():
    """Фамилия матчится строго по границам токена, а не как подстрока внутри слова."""
    data = oa_data(
        title="Randomized clinical outcomes in surgery",
        authors=("Wei Lin",),
    )
    # 'lin' содержится внутри транслита 'klinicheskie', но не является отдельным токеном
    fact = "Иванов А.А. — Клинические аспекты наблюдения"
    status, detail = classify_fact_match(fact, data)
    assert status == "UNCERTAIN"
    assert "author 'Lin' found" not in detail


def test_same_author_unrelated_paper_ru_en_is_uncertain_not_confirmed():
    """Нерелевантная статья того же автора/соавтора при языковом барьере → UNCERTAIN, не CONFIRMED."""
    data_first = oa_data(
        title="Quantum dots in semiconductor physics",
        authors=("Nikita S. Popov",),
    )
    fact_first = "Попов Н.С. — Морфологическая оценка состояния печени"
    status1, detail1 = classify_fact_match(fact_first, data_first)
    assert status1 == "UNCERTAIN"
    assert "author matched without title confirmation" in detail1
    assert check_fact_match(fact_first, data_first)[0] is False

    data_co = oa_data(
        title="Quantum dots in semiconductor physics",
        authors=("Valeria Schestakova", "S. A. Donskov"),
    )
    fact_co = "Донсков С.А. — Морфологическая оценка состояния печени"
    status2, detail2 = classify_fact_match(fact_co, data_co)
    assert status2 == "UNCERTAIN"
    assert "author matched without title confirmation" in detail2


def test_short_stems_do_not_false_match_inside_unrelated_words():
    """Короткие корни ('ген', 'рак', 'вен') не срабатывают внутри посторонних слов."""
    data = oa_data(
        title="General study of cancer and vein degeneration with excellent outcomes",
        authors=("John Smith",),
    )
    fact = "Иванов А.А. — Характеристика проведения рентгеновского патогена"
    status, detail = classify_fact_match(fact, data)
    assert status == "UNCERTAIN"
    assert "title overlap only 0%" in detail


def test_single_cognate_without_author_under_language_barrier_is_uncertain():
    """Одиночное совпадение слова без автора при языковом барьере слишком слабо для CONFIRMED."""
    data = oa_data(
        title="Clinical outcomes in orthopedic surgery",
        authors=("John Smith",),
    )
    fact = "Иванов А.А. — Клиническое наблюдение"
    status, _ = classify_fact_match(fact, data)
    assert status == "UNCERTAIN"


def test_latin_surname_substring_does_not_match():
    """И в латинице фамилия 'Smith' не должна матчиться внутри 'Smithson'."""
    data = oa_data(
        title="Completely unrelated astrophysics paper",
        authors=("John Smith",),
    )
    fact = "Smithson A. — Polymer chemistry synthesis"
    status, detail = classify_fact_match(fact, data)
    assert status == "MISMATCH"
    assert "NOT in fact" in detail


def test_latin_same_author_different_paper_returns_uncertain():
    """EN↔EN: тот же автор, но другая статья (0% совпадения темы) → UNCERTAIN, не CONFIRMED."""
    data = oa_data(
        title="Deep learning for pediatric chest radiographs",
        authors=("Eric Topol",),
    )
    fact = "Topol E.J. — Quantum dots in semiconductor physics"
    status, detail = classify_fact_match(fact, data)
    assert status == "UNCERTAIN"
    assert "author-only match without title confirmation" in detail
    assert check_fact_match(fact, data)[0] is False


def test_multiple_russian_words_same_english_concept_not_double_counted():
    """Две русские словоформы («сердечная» и «сердца») на одном EN-слове ('cardiac') = 1 совпадение."""
    from pipeline.biomed.factcheck_biomed import check_biomed_fact_match

    data_oa = oa_data(
        title="Cardiac rehabilitation outcomes in elderly volunteers",
        authors=("John Smith",),
    )
    fact = "Иванов А.А. — Сердечная недостаточность сердца"
    status_oa, detail_oa = classify_fact_match(fact, data_oa)
    assert status_oa == "UNCERTAIN"
    assert "(1/3 words)" in detail_oa

    # То же правило в BioMed (Ур.0.7): одно EN-слово 'cardiac' не даёт ложный CONFIRMED
    data_bm = {
        "title": "Cardiac rehabilitation outcomes in elderly volunteers",
        "first_author": "Smith J",
        "authors": ["Smith J"],
    }
    status_bm, detail_bm = check_biomed_fact_match(fact, data_bm)
    assert status_bm == "UNCERTAIN"
    assert "(1/3 words)" in detail_bm
