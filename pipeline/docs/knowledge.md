# knowledge.md — Каскад веб-фактчекинга

> **Цель:** помочь агенту быстро выбрать надёжный путь и выполнить задачу с минимумом итераций.
> **Принцип:** доставить 90% результата за 30 минут лучше, чем 100% за 3 часа.
>
> **Правка .docx:** см. отдельный протокол — [`docx-protocol.md`](docx-protocol.md).

---

## 0. Каскад веб-фактчекинга (7 уровней)

> **Единый источник правды по схеме каскада:** [`cascade.md`](cascade.md) — уровни, правила эскалации, словарь вердиктов. Ниже — только краткая справка.

1. **Правка .docx:** любые задачи (форматирование, вставка фрагментов, таблицы, заголовки) — через `python-docx`. См. [`docx-protocol.md`](docx-protocol.md).
2. **Веб-фактчекинг (каскадный водопад):** проверка существования статей, DOI, URL — 7 уровней: OpenAlex (Ур.0.5), researcher-web (Ур.1), Crawl4AI (Ур.2), Scrapling (Ур.3), FireCrawl (Ур.4, платный резерв), Человек (Ур.5), Gemini DeepSearch (Ур.6). Правила эскалации и словарь вердиктов: [`cascade.md`](cascade.md).

### 0.1 Технические константы (НЕ угадывать пути)

> **Почему MAX_TEXT_CHARS/TRUNCATE_KEEP_CHARS различаются:**
> - Crawl4AI и Scrapling: `MAX_TEXT_CHARS = 200_000`, `TRUNCATE_KEEP_CHARS = 1_500` — парсят полные HTML-страницы (могут быть очень большими), 1500 символов достаточно для Cloudflare-заглушек и error-страниц.
> - OpenAlex: `MAX_TEXT_CHARS = 50_000`, `TRUNCATE_KEEP_CHARS = 2_000` — ответы API это структурированный JSON, всегда компактный. 2000 символов нужно чтобы захватить полное сообщение об ошибке от API.

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

### 0.2 OpenAlex API (Ур.0.5 каскада — программная валидация DOI)

Когда применять:
- **Всегда первым делом** для URL, содержащих doi.org или DOI в поле expect
- Мгновенная проверка существования статьи через OpenAlex REST API (без парсинга страниц)
- Если OpenAlex НЕ нашёл статью (NOT_FOUND) → передать на Ур.1 (researcher-web + Crawl4AI)

Когда НЕ применять:
- URL без DOI (minzdrav.gov.ru, iris.who.int, ohri.ca) → сразу Ур.1
- Уже проверенные DOI (избегать повторных запросов)

API (проверено на OpenAlex REST API, CC0):
- `GET https://api.openalex.org/works/https://doi.org/{DOI}?mailto={email}`
- Без аутентификации. С `mailto` — Polite Pool (100k запросов/день).
- Возвращает: `title`, `authorships`, `publication_year`, `primary_location` (journal, volume, pages), `cited_by_count`, `doi`.
- 404 = статья не найдена (NOT_FOUND).

Технические константы:
- **venv:** корневой (`.venv/Scripts/python.exe` на Windows)
- **Скрипт-раннер:** `pipeline/openalex/factcheck_openalex.py`
- **Запуск:** `.venv/Scripts/python.exe pipeline/openalex/factcheck_openalex.py --targets pipeline/targets.json --prefix oa --timeout 15`
- **Аргументы:** `--targets`, `--prefix` (default: `oa`), `--timeout` (сек, default: 15), `--mailto` (email для Polite Pool)
- **Выходные файлы:** `workspace/{prefix}_{id}.txt` (формат совместим с Crawl4AI)
- **Таймаут:** 15 сек на запрос (API, быстро)
- **Зависимости:** только стандартная библиотека (urllib.request)
- **Стоимость:** бесплатно (OpenAlex CC0, без ключа)

### 0.3 Scrapling (Ур.3 каскада — замена FireCrawl, бесплатно)

Когда применять:
- URL вернул EMPTY/Cloudflare-маркер/TIMEOUT на Crawl4AI (Ур.2)
- Сайт с известной anti-bot защитой (Cloudflare Turnstile, DataDome)
- Пере-парсинг URL с изменённой структурой (`--adaptive`)

Когда НЕ применять:
- Простые статические URL (используй Crawl4AI — быстрее)

API (проверено на scrapling v0.4.11):
- `StealthySession(headless=True)` — **синхронный** `with` (не async). Держит браузер открытым между запросами — 10-20× быстрее one-off.
- `session.fetch(url, timeout=ms, network_idle=True)` — timeout в **миллисекундах**.
- `page.get_all_text()` — BEST: извлекает plain text (возвращает `TextHandler`, нужен `str()`).
- `str(page.html_content)` — FALLBACK: HTML-код страницы.
- `page.body.decode('utf-8')` — FALLBACK: raw body.
- `page.css('.selector', adaptive=True)` — adaptive пере-парсинг при смене структуры сайта.
- `page.status` — HTTP-статус.
- `page.markdown` — **НЕ СУЩЕСТВУЕТ** (в отличие от Crawl4AI).
- `page.text` (`TextHandler`) — `str()` возвращает пустую строку. НЕ ИСПОЛЬЗОВАТЬ.
- `extract_text()` в скрипте — безопасный fallback: `get_all_text → html_content → body.decode`.

Технические константы:
- **venv:** корневой (`.venv/Scripts/python.exe` на Windows)
- **Скрипт-раннер:** `pipeline/scrapling/factcheck_scrapling.py`
- **Запуск:** `.venv/Scripts/python.exe pipeline/scrapling/factcheck_scrapling.py --targets pipeline/targets.json --prefix sc --timeout 90`
- **Аргументы:** `--targets`, `--prefix` (default: `sc`), `--timeout` (сек, default: 90), `--adaptive`, `--css-selector`, `--no-cloudflare`
- **Выходные файлы:** `workspace/{prefix}_{id}.txt` (формат совместим с Crawl4AI)
- **Таймаут:** 90 сек на URL (браузер медленнее HTTP). Конвертится в ms внутри скрипта.
- **Браузеры:** `%USERPROFILE%\AppData\Local\ms-playwright\` (Windows)
- **Стоимость:** бесплатно (локальный Playwright, не расходует кредиты FireCrawl)

### 0.4 FireCrawl (РЕЗЕРВНЫЙ — Ур.4 каскада)

> **ПОНИЖЕН:** приоритет отдан Scrapling (Ур.3). FireCrawl — только если Scrapling не справился.

Когда применять:
- Scrapling (Ур.3) вернул EMPTY/ERROR/пустой контент
- Сайт с неизвестной anti-bot защитой, которую не берёт Scrapling
- Требуется гарантированный markdown-вывод (Scrapling не имеет `page.markdown`)

Использование:
- `firecrawl scrape 'https://...' -o workspace/firecrawl_<name>.md`
- `firecrawl credit-usage` — **обязательно** в конце каждого сеанса
- См. [`firecrawl.md`](../firecrawl/firecrawl.md) для полного референса

### 0.5 ОБЯЗАТЕЛЬНО: отчёт о кредитах FireCrawl в конце

После **каждого** сеанса веб-фактчекинга, где использовался FireCrawl (даже если results.md не создаётся), последним шагом:
1. Выполнить `firecrawl credit-usage`
2. Записать в `results.md` (или в ответ пользователю) точные цифры: использовано X / осталось Y (Z%)
3. НЕ придумывать цифры — только из вывода команды

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
- Каскад 7 уровней: [`cascade.md`](cascade.md) — схема водопада, правила эскалации, словарь вердиктов.
- Корневой .venv = `.venv/Scripts/python.exe` (Windows) или `.venv/bin/python` (Linux/Mac).
- **OpenAlex (Ур.0.5):** `pipeline/openalex/factcheck_openalex.py` — всегда первым для DOI.
- **Crawl4AI (Ур.2):** `pipeline/crawl4ai/factcheck_crawl4ai.py` — базовый парсинг. Если EMPTY → Scrapling.
- **Scrapling (Ур.3, бесплатно):** `pipeline/scrapling/factcheck_scrapling.py` — обход Cloudflare.
- **FireCrawl (Ур.4, резерв):** `firecrawl credit-usage` **обязательно** если использовался → цифры в results.md.

**Главное:** надёжность через простоту. Один Python-скрипт, исполненный за 0.01 сек, лучше 8 CLI-команд за 20 секунд.

---

## Связанные документы

- [`docx-protocol.md`](docx-protocol.md) — полный протокол правки .docx через python-docx
- [`architecture.md`](architecture.md) — архитектура конвейера редактуры
- [`../openalex/openalex.md`](../openalex/openalex.md) — standalone-референс OpenAlex
- [`../scrapling/scrapling.md`](../scrapling/scrapling.md) — standalone-референс Scrapling
- [`../firecrawl/firecrawl.md`](../firecrawl/firecrawl.md) — standalone-референс FireCrawl
