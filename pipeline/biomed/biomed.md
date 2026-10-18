# biomed.md — Уровень 0.7: BioMed Deep Check (PubMed / Europe PMC)

> **Назначение:** Быстрая верификация биомедицинских публикаций по PMID и PMCID через открытые REST API (NCBI E-utilities и Europe PMC).
> **Позиция в каскаде:** Ур. 0.7 — располагается между Ур. 0.5 (OpenAlex) и браузерными краулерами (Ур. 2 Crawl4AI, Ур. 3 Scrapling). Для медицинских и биологических фактов позволяет подтвердить данные без запуска тяжёлых браузеров.

---

## 1. Команды запуска

```bash
# Базовый запуск по целям targets.json (Windows):
.venv/Scripts/python.exe pipeline/biomed/factcheck_biomed.py --targets pipeline/targets.json --prefix bm --timeout 15

# Базовый запуск (Linux / macOS):
.venv/bin/python pipeline/biomed/factcheck_biomed.py --targets pipeline/targets.json --prefix bm --timeout 15

# Проверка плана без выполнения сетевых запросов:
.venv/Scripts/python.exe pipeline/biomed/factcheck_biomed.py --targets pipeline/targets.json --dry-run

# Отключение кросс-проверки соответствия факт-строки метаданным:
.venv/Scripts/python.exe pipeline/biomed/factcheck_biomed.py --targets pipeline/targets.json --no-crosscheck
```

---

## 2. Формат выходных артефактов

Результаты записываются в директорию `workspace/bm_{id}.txt`:

```text
URL: https://pubmed.ncbi.nlm.nih.gov/35113657/
FACT: Smith J. — Epigenetic regulation of cardiac hypertrophy
EXPECT: PMID: 35113657
PMID: 35113657
STATUS: CONFIRMED
TITLE: Epigenetic regulation of cardiac hypertrophy and heart failure.
AUTHORS: Smith J; Doe A; Johnson K.
JOURNAL: Nature Cardiovascular Research
YEAR: 2022
VOLUME: 1
PAGES: 120-135
DOI: 10.1038/s44161-021-00012-3
PMCID: PMC8912345
API: NCBI E-utilities
```

---

## 3. Статусы выполнения и коды выхода

* `CONFIRMED`: Статья найдена в базе, и ключевые слова названия/фамилия первого автора совпали с факт-строкой.
* `MISMATCH`: Идентификатор PMID/PMC существует, но автор или тема статьи кардинально расходятся с факт-строкой (галлюцинация LLM или подмена источника).
* `ERROR`: Ошибка сети, превышение таймаута или статья не найдена (404).
* `SKIP`: В объекте цели не обнаружены признаки биомедицинских идентификаторов (PMID/PMC).

**Коды выхода CLI:**
* `0`: Все биомедицинские цели подтверждены (`CONFIRMED`) или пропущены (`SKIP`).
* `1`: Обнаружен хотя бы один `MISMATCH` (требуется ручной разбор рецензентом).
* `2`: Ошибка аргументов или некорректный файл целей.
