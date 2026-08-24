---
name: factcheck
description: "Cascade web fact-checking: OpenAlex DOI validation → Crawl4AI scraping → Scrapling Cloudflare bypass → FireCrawl reserve. 8-level cascade for verifying scientific references, DOIs, URLs, and web facts. Use when the user needs to verify bibliography, check article existence, validate DOIs, scrape web content, or fact-check claims against online sources."
---
# FactCheck — Каскад веб-фактчекинга

> **Назначение:** портируемый скилл для проверки фактов, DOI, URL и веб-контента.
> **Принцип:** доставить 90% результата за 30 минут лучше, чем 100% за 3 часа.
> **Правка .docx:** см. скилл `hush-docx` (механические правки) или `docx` (полный OOXML).

---

## 0. Каскад (8 уровней)

```
Ур.0.5 → OpenAlex API           (мгновенная проверка DOI, бесплатно)
Ур.1   → researcher-web         (поиск фактов)
Ур.2   → Crawl4AI               (базовый HTTP-парсинг)
Ур.2.5 → Playwright MCP         (интерактивный браузер, KEYLESS)
Ур.3   → Scrapling              (обход Cloudflare, бесплатно)
Ур.4   → FireCrawl              (платный резерв)
Ур.5   → Человек                (ручная верификация)
Ур.6   → Gemini DeepSearch      (опционально)
```

### Когда применять каждый уровень

| Уровень | Инструмент | Когда | Команда |
|---------|-----------|-------|---------|
| **0.5** | OpenAlex | DOI в URL или expect | `python scripts/factcheck_openalex.py --targets targets.json --prefix oa` |
| **1** | researcher-web | Базовые факты, поиск | Встроен в FreeBuff |
| **2** | Crawl4AI | Любой URL, статические страницы | `python scripts/factcheck_crawl4ai.py --targets targets.json --prefix crawl` |
| **2.5** | Playwright MCP | Логин, формы, JS-тяжёлые SPA | `npx -y @playwright/mcp@latest` (MCP) |
| **3** | Scrapling | Cloudflare, anti-bot защита | `python scripts/factcheck_scrapling.py --targets targets.json --prefix sc` |
| **4** | FireCrawl | Резерв — если Scrapling не справился | `firecrawl scrape 'https://...' -o output.md` |

---

## 1. Установка зависимостей

### Минимальная (только OpenAlex — без внешних библиотек)

OpenAlex работает на **стандартной библиотеке Python** (urllib.request). Никаких дополнительных пакетов не требуется.

```bash
python scripts/factcheck_openalex.py --targets targets.json --prefix oa
```

### Полная установка (OpenAlex + Crawl4AI + Scrapling)

```bash
# 1. Создать виртуальное окружение
python -m venv .venv

# 2. Активировать (Windows)
.venv\Scripts\activate
# или (Linux/Mac)
source .venv/bin/activate

# 3. Установить зависимости
pip install -r requirements.txt

# 4. Установить браузер для Playwright (нужен Scrapling)
playwright install chromium

# 5. Проверить
python -c "import crawl4ai; print('crawl4ai OK')"
python -c "from scrapling.fetchers import StealthySession; print('scrapling OK')"
python -c "from docx import Document; print('docx OK')"
```

### Зависимости (requirements.txt)

```
crawl4ai>=0.5.0
scrapling[all]>=0.4.11
python-docx>=1.0.0
```

---

## 2. Быстрый старт

### 2.1 Подготовить targets.json

```json
[
  {
    "id": "ref01",
    "url": "https://doi.org/10.1038/s41591-018-0300-7",
    "fact": "Topol E.J. High-performance medicine. Nature Medicine 2019",
    "expect": "DOI 10.1038/s41591-018-0300-7"
  },
  {
    "id": "ref02",
    "url": "https://www.bmj.com/content/372/bmj.n71",
    "fact": "Page M.J. et al. The PRISMA 2020 statement. BMJ 2021",
    "expect": ""
  }
]
```

**Обязательные поля:** `id`, `fact`, `url`
**Опциональные:** `expect` (ожидаемое значение — DOI, название журнала, etc.)

### 2.2 Запустить каскад

```bash
# Шаг 1: OpenAlex — мгновенная проверка DOI
python scripts/factcheck_openalex.py --targets targets.json --prefix oa --timeout 15

# Шаг 2: Crawl4AI — парсинг страниц для тех, кто без DOI или NOT_FOUND
python scripts/factcheck_crawl4ai.py --targets targets.json --prefix crawl --timeout 45

# Шаг 3: Scrapling — обход Cloudflare для EMPTY/TIMEOUT с Crawl4AI
python scripts/factcheck_scrapling.py --targets targets_retry.json --prefix sc --timeout 90
```

### 2.3 Прочитать результаты

Все скрипты сохраняют результаты в `./factcheck_output/{prefix}_{id}.txt` (формат совместим между всеми тремя скриптами).

---

## 3. Формат выходного файла

```
URL: https://doi.org/10.1136/bmj.n71
FACT: Page M.J. et al. The PRISMA 2020 statement...
EXPECT: DOI 10.1136/bmj.n71
DOI: 10.1136/bmj.n71
STATUS: CONFIRMED
SUCCESS: True

======================================================================
OpenAlex Title      : The PRISMA 2020 statement: an updated guideline...
OpenAlex Authors     : Matthew J. Page; Joanne E. McKenzie; ...
OpenAlex DOI         : 10.1136/bmj.n71
OpenAlex Biblio      : Journal: BMJ, Year: 2021, Volume: 372
OpenAlex Cited by    : 97026
```

---

## 4. CLI-аргументы (общие для всех скриптов)

| Аргумент | OpenAlex | Crawl4AI | Scrapling | Описание |
|----------|:--------:|:--------:|:---------:|----------|
| `--targets` | ✅ | ✅ | ✅ | Путь к targets.json |
| `--prefix` | ✅ `oa` | ✅ `crawl` | ✅ `sc` | Префикс выходных файлов |
| `--timeout` | ✅ `15` | ✅ `45` | ✅ `90` | Таймаут (сек) |
| `--out-dir` | ✅ | ✅ | ✅ | Директория вывода (по умолч.: `./factcheck_output/`) |
| `--mailto` | ✅ | — | — | Email для OpenAlex Polite Pool |
| `--no-cache` | — | ✅ | — | Отключить кеш Crawl4AI |
| `--js-code` | — | ✅ | — | JS для инъекции после загрузки |
| `--session` | — | ✅ | — | ID сессии для сохранения кук |
| `--adaptive` | — | — | ✅ | Adaptive-парсинг для меняющихся сайтов |
| `--css-selector` | — | — | ✅ | CSS-селектор для извлечения контента |
| `--no-cloudflare` | — | — | ✅ | Отключить обход Cloudflare |

---

## 5. OpenAlex (Ур.0.5) — API-референс

**Эндпоинт:** `GET https://api.openalex.org/works/https://doi.org/{DOI}?mailto={email}`

**Бесплатно:** CC0, без API-ключа, без регистрации.

**Ключевые поля ответа:** `title`, `doi`, `publication_year`, `cited_by_count`, `type`, `authorships[].author.display_name`, `primary_location.source.display_name`, `primary_location.biblio` (volume, first_page, last_page).

**Извлечение DOI:** скрипт ищет DOI в `url` (doi.org/...) и в поле `expect` (паттерн `DOI 10.xxx/...`).

**HTTP-статусы:**
- 200 + fact совпадает → CONFIRMED
- 200 + fact НЕ совпадает → **MISMATCH** (DOI реален, но описание не соответствует статье — возможна фальсификация)
- 404 → NOT_FOUND → передать на Ур.1/2
- 429 → Rate limit → повторить с паузой

**Кросс-проверка MISMATCH:** скрипт сравнивает fact-строку с реальными метаданными OpenAlex (фамилия первого автора + ключевые слова из названия). Если ни автор, ни тема не совпадают — статус MISMATCH. Это ловит фальсификации, где DOI реален, но описание подделано (эмпирический кейс: источник #26, тест 2026-07-19).

**Ограничения:** только DOI; не все статьи есть в индексе (особенно русскоязычные, свежие); без `--mailto` — ~10k запросов/день, с `--mailto` — 100k/день.

---

## 6. Crawl4AI (Ур.2) — референс

**API:** `AsyncWebCrawler().arun(url, cache_mode=CacheMode.ENABLED)`

**Вывод:** `result.markdown` (Markdown-текст страницы), `result.links` (все ссылки на странице).

**CacheMode:** по умолчанию ENABLED (экономит время на повторных URL). `--no-cache` для отключения.

**Когда Crawl4AI даёт EMPTY:**
- JS-тяжёлые SPA → использовать `--js-code` для инъекции
- Cloudflare/anti-bot → передать на Ур.3 (Scrapling)
- Сайт требует логина → передать на Ур.2.5 (Playwright MCP)

---

## 7. Scrapling (Ур.3) — референс

**API (sync):** `StealthySession(headless=True, solve_cloudflare=True).fetch(url, timeout=ms, network_idle=True)`

**Извлечение текста (приоритет):**
1. `page.get_all_text()` → чистый текст (BEST)
2. `str(page.html_content)` → HTML (fallback)
3. `page.body.decode('utf-8')` → raw bytes (last resort)

**Что НЕ работает:** `page.markdown` (не существует — отличие от Crawl4AI), `page.text` (TextHandler возвращает пустую строку).

**Batch-режим:** `StealthySession` держит браузер открытым между URL → 10-20× быстрее, чем открывать/закрывать для каждого.

**Cloudflare:** `solve_cloudflare=True` по умолчанию. `--no-cloudflare` для отключения (быстрее на простых сайтах).

---

## 8. Ручной фактчекинг (без скриптов)

Если скрипты не справляются — используй `researcher-web` для поиска фактов:

```
researcher-web: "проверь, существует ли статья Topol E.J. High-performance medicine Nature Medicine 2019"
```

Или `read_url` для прямого парсинга страниц:

```
read_url("https://www.nature.com/articles/s41591-018-0300-7", max_chars=5000)
```

---

## 9. Формат отчёта

После каждого прогона фактчекинга формируй отчёт:

```markdown
# Отчёт факт-чекера

## Сводка
| Статус | Количество |
|--------|-----------|
| CONFIRMED | N |
| MISMATCH | M |
| REFUTED | 0 |
| UNCERTAIN | 0 |
| BLOCKED | 0 |

## Детали по каждому факту

### ФАКТ 1: [название]
- Статус: CONFIRMED
- Значение: [метаданные из OpenAlex/Crawl4AI]
- Источник: [URL]
- Метод: OpenAlex / Crawl4AI / Scrapling
- Доказательство: [цитата из выходного файла]
```

**Правила:**
- НИКОГДА не выдумывай подтверждения. Если не нашёл — `UNCERTAIN`
- НЕ утверждай, что факт галлюцинация, если не проверил прямым URL
- Если Crawl4AI вернул Cloudflare → передай на Scrapling (Ур.3)
- Если Scrapling не справился → `BLOCKED`, а не `CONFIRMED`

---

## 10. API для вызова из Python

```python
# Импорт функций из скриптов скилла
import sys
sys.path.insert(0, '.agents/skills/factcheck/scripts')

from factcheck_openalex import extract_doi, lookup_doi, batch_lookup
from factcheck_crawl4ai import crawl_one

# Проверить DOI
doi = extract_doi({"url": "https://doi.org/10.1136/bmj.n71", "expect": ""})
data, error = lookup_doi(doi, timeout=15, mailto="me@example.com")

# Пакетный запуск
targets = [{"id": "ref01", "url": "...", "fact": "..."}]
results = batch_lookup(targets, prefix="oa", timeout=15, mailto="me@example.com")
```

---

## 11. Связанные скиллы

| Скилл | Назначение |
|-------|-----------|
| `hush-docx` | Механические правки .docx (python-docx) |
| `docx` | Полный OOXML (схемы, tracked changes, pack/unpack) |
| `firecrawl` | Платный резерв для веб-скрапинга (CLI `firecrawl scrape`) |

## Связанные документы в проекте

| Файл | Назначение |
|------|-----------|
| `pipeline/docs/architecture.md` | Архитектура конвейера split-and-merge |
| `pipeline/docs/knowledge.md` | Полный протокол фактчекинга + техконстанты |
| `pipeline/docs/results.md` | Пример отчёта фактчекера |
| `pipeline/targets.json` | Пример файла целей |
