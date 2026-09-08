# knowledge.md — Каскад веб-фактчекинга

> **Цель:** помочь агенту быстро выбрать надёжный путь и выполнить задачу с минимумом итераций.
> **Принцип:** доставить 90% результата за 30 минут лучше, чем 100% за 3 часа.
>
> **Правка .docx:** см. отдельный протокол — [`docx-protocol.md`](docx-protocol.md).

---

## 0. Каскад веб-фактчекинга

> **Схема 7 уровней, правила эскалации, словарь вердиктов — только в [`cascade.md`](cascade.md). Здесь схему не дублируем.**
> Смежная тема: правка `.docx` — только в [`docx-protocol.md`](docx-protocol.md).

### 0.1 Технические константы — ЕДИНСТВЕННЫЙ источник (НЕ угадывать пути)

> venv, команды запуска, выходные файлы, очистка `workspace/` — только здесь. Референсы уровней на этот раздел ссылаются и не дублируют его.

> **Почему MAX_TEXT_CHARS/TRUNCATE_KEEP_CHARS различаются:**
> - Crawl4AI и Scrapling: `MAX_TEXT_CHARS = 200_000`, `TRUNCATE_KEEP_CHARS = 1_500` — парсят полные HTML-страницы (могут быть очень большими), 1500 символов достаточно для Cloudflare-заглушек и error-страниц.
> - OpenAlex: констант нет — ответы API это структурированный JSON, всегда компактный, сохраняются целиком без урезания.

- **Корневой venv:** `.venv/Scripts/python.exe` (Windows) или `.venv/bin/python` (Linux/Mac). Относительно корня проекта. **НИКОГДА не искать python глобально — всегда использовать корневой .venv.**
- **Запуск OpenAlex:** `.venv/Scripts/python.exe pipeline/openalex/factcheck_openalex.py --targets pipeline/targets.json --prefix oa --timeout 15`
- **Запуск Crawl4AI:** `.venv/Scripts/python.exe pipeline/crawl4ai/factcheck_crawl4ai.py --targets pipeline/targets.json --prefix <prefix> --timeout 45`
- **Запуск Scrapling:** `.venv/Scripts/python.exe pipeline/scrapling/factcheck_scrapling.py --targets pipeline/targets.json --prefix sc --timeout 90`
- **Выходные файлы (все уровни):** `workspace/{prefix}_{id}.txt` — OpenAlex (`oa_*`), Crawl4AI (`crawl_*`), Scrapling (`sc_*`); FireCrawl — `workspace/firecrawl_<name>.md` через `-o workspace/firecrawl_<name>.md`. Директория `workspace/` — в корне репо, вне git. **НЕ создавай других каталогов для артефактов.**
- **Проверка кредитов FireCrawl:** `firecrawl credit-usage`
- **Полный референс команд OpenAlex:** см. [`openalex.md`](../openalex/openalex.md)
- **Полный референс команд Scrapling:** см. [`scrapling.md`](../scrapling/scrapling.md)
- **Полный референс команд FireCrawl:** см. [`firecrawl.md`](../firecrawl/firecrawl.md)
- **Очистка временных файлов после сеанса:** удалить `workspace/` целиком (или только `{prefix}_*.txt` внутри неё). Если создавался `targets_retry.json` — он тоже лежит в `workspace/`. Сами результаты уже в `results.md`.
- **python-docx:** устанавливается через `pip install python-docx`. Использует стандартный Python (или корневой .venv, если python-docx установлен там).

### 0.2 OpenAlex — детали уровня

> Когда применять, API, аргументы — только в [`../openalex/openalex.md`](../openalex/openalex.md), здесь не дублируются.

### 0.3 Scrapling — детали уровня

> API, `extract_text()`, аргументы — только в [`../scrapling/scrapling.md`](../scrapling/scrapling.md), здесь не дублируются.

### 0.4 FireCrawl — детали уровня

> Когда применять и команды — только в [`../firecrawl/firecrawl.md`](../firecrawl/firecrawl.md), здесь не дублируются.

### 0.5 ОБЯЗАТЕЛЬНО: отчёт о кредитах FireCrawl в конце

После **каждого** сеанса веб-фактчекинга, где использовался FireCrawl (даже если results.md не создаётся), последним шагом:
1. Выполнить `firecrawl credit-usage`
2. Записать в `results.md` (или в ответ пользователю) точные цифры: использовано X / осталось Y (Z%)
3. НЕ придумывать цифры — только из вывода команды

---

### 0.6 Быстрый режим без зависимостей

> Workflow, конвенция имён, команды, дефект DOI-сверки — только в [`../manual/manual.md`](../manual/manual.md), здесь не дублируются.

---

## 1. Аудит инструментов (2026-07-16)

> Проведён полный аудит: скачана официальная документация OpenAlex, Crawl4AI, Scrapling. Сравнено с нашими скриптами и .md-документацией. Результаты внедрены в код.

### Сводка использования

| Инструмент | Ур. | Было | Стало | Главное улучшение |
|-----------|:---:|:---:|:---:|---|
| **OpenAlex** | 0.5 | 90% | 95% | +ids (PMID/PMC), +OA-статус, +PDF-ссылки |
| **Crawl4AI** | 2 | 30% | 60% | +CacheMode, +.links, +js_code, +session |
| **Scrapling** | 3 | 95% | 95% | +документирован selectolax-парсинг |

### Что изменилось в коде

- **Crawl4AI v5:** `CacheMode.ENABLED` по умолчанию, `--no-cache` для отключения. `--js-code` для инъекции JS (решает EMPTY). `--session` для сохранения кук. Вывод `.links` в выходной файл.
- **OpenAlex v2:** вывод кросс-идентификаторов (`ids`: PMID, PMCID, MAG) и OA-статуса с PDF-ссылками (`locations`) в выходной файл.
- **scrapling.md:** документирован selectolax-парсинг (find, find_all, attributes, get, matches).

### Приоритеты на будущее

1. Crawl4AI: LLMExtractionStrategy для структурированного извлечения метаданных
2. Crawl4AI: concurrency (asyncio.gather) для параллельного обхода
3. Crawl4AI: BrowserConfig (viewport, user_agent, wait_for)

---

## 2. TL;DR (выучить наизусть)

**Для правки .docx:** см. [`docx-protocol.md`](docx-protocol.md) — полный протокол (правила, шаблоны, антипаттерны). Для рутинных механических правок используется навык `hush-docx` (набор хелперов `python-docx`, проверен на 6 документах: 10/10, 0.065 сек).

**Для веб-фактчекинга:**
- Схема, эскалация, вердикты — только [`cascade.md`](cascade.md).
- Команды и пути — только §0.1 выше.
- Быстрый режим — только [`../manual/manual.md`](../manual/manual.md).

**Главное:** надёжность через простоту. Один Python-скрипт, исполненный за 0.01 сек, лучше 8 CLI-команд за 20 секунд.

---

## Связанные документы

- [`docx-protocol.md`](docx-protocol.md) — полный протокол правки .docx через python-docx
- [`architecture.md`](architecture.md) — архитектура конвейера редактуры
- [`../openalex/openalex.md`](../openalex/openalex.md) — standalone-референс OpenAlex
- [`../scrapling/scrapling.md`](../scrapling/scrapling.md) — standalone-референс Scrapling
- [`../firecrawl/firecrawl.md`](../firecrawl/firecrawl.md) — standalone-референс FireCrawl
