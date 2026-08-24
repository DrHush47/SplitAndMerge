# OpenAlex API — Ур.0.5 каскада факт-чекинга

> **Standalone-референс для агента.** В новой сессии без контекста — читай этот документ.
> **Основной инструмент:** `openalex/factcheck_openalex.py`
> **Пути:** относительно папки `pipeline/`. Для запуска из корня проекта — `./pipeline/crawl4ai/.venv/...` (см. `../docs/knowledge.md` §0.1).
> **Вендор:** [openalex.org](https://openalex.org) — открытый индекс научных работ (CC0)
> **Лицензия:** CC0 (данные), MIT (скрипт)

## Роль в каскаде

```
Ур.0.5 → OpenAlex API           ← ТЫ ЗДЕСЬ (бесплатно, мгновенная проверка DOI)
Ур.1   → researcher-web         (поиск фактов)
Ур.2   → Crawl4AI               (базовый HTTP-парсинг)
Ур.2.5 → Playwright MCP         (интерактивный браузер, KEYLESS)
Ур.3   → Scrapling StealthySession (обход Cloudflare, бесплатно)
Ур.4   → FireCrawl              (резерв, платный)
Ур.5   → Человек                (ручная верификация)
Ур.6   → Gemini DeepSearch      (опционально)
```

**Когда применять OpenAlex:**
- **Всегда первым делом** для URL, содержащих `doi.org` или DOI в поле `expect`
- Мгновенная проверка существования статьи через REST API без парсинга страниц
- Если OpenAlex НЕ нашёл статью (NOT_FOUND) → передать на Ур.1 (researcher-web + Crawl4AI)

**Когда НЕ применять:**
- URL без DOI (minzdrav.gov.ru, iris.who.int, ohri.ca) → сразу Ур.1
- Уже проверенные DOI (избегать повторных запросов)

---

## Quick start

```bash
# Windows
./crawl4ai/.venv/Scripts/python.exe openalex/factcheck_openalex.py --targets targets.json --prefix oa --timeout 15

# Linux/Mac
./crawl4ai/.venv/bin/python openalex/factcheck_openalex.py --targets targets.json --prefix oa --timeout 15

# С кастомным email для Polite Pool (100k запросов/день)
./crawl4ai/.venv/Scripts/python.exe openalex/factcheck_openalex.py --targets targets.json --prefix oa --mailto your@email.com
```

Результат: `openalex/oa_{id}.txt` для каждого URL с DOI.

---

## Формат targets.json

```json
[
  {"id": "ref01", "url": "https://doi.org/10.1038/s41591-018-0301-7", "fact": "Topol E.J. ...", "expect": "DOI 10.1038/s41591-018-0300-7"},
  {"id": "ref02", "url": "https://www.nature.com/articles/s41591-018-0301-7", "fact": "...", "expect": "DOI 10.1038/s41591-018-0300-7"}
]
```

**Обязательные поля:** `id`, `fact`, `url`
**Опциональные:** `expect` (если содержит DOI — скрипт извлечёт его для lookup)

**Как скрипт находит DOI:**
1. Прямой `doi.org` URL — извлекает DOI из URL
2. `expect` поле с паттерном `DOI 10.xxx/...` — извлекает DOI оттуда
3. Если ни там, ни там — SKIP

---

## CLI-аргументы

| Аргумент | По умолч. | Описание |
|---|---|---|
| `--targets` | (required) | Путь к JSON-файлу с целями |
| `--prefix` | `oa` | Префикс выходных файлов |
| `--timeout` | `15` | Таймаут на запрос в **секундах** |
| `--mailto` | `factcheck@example.com` | Email для OpenAlex Polite Pool (100k запросов/день вместо ~10k) |

---

## Технические константы

| Параметр | Значение |
|---|---|
| **venv** | `./crawl4ai/.venv/Scripts/python.exe` (Windows) / `./crawl4ai/.venv/bin/python` (Linux/Mac) |
| **Скрипт** | `openalex/factcheck_openalex.py` |
| **Выходные файлы** | `openalex/{prefix}_{id}.txt` |
| **Таймаут** | 15 сек (REST API, быстро) |
| **Зависимости** | Только стандартная библиотека (`urllib.request`) |
| **Стоимость** | Бесплатно (OpenAlex CC0, без API-ключа, без регистрации) |

---

## API OpenAlex (REST, без аутентификации)

### Эндпоинт

```
GET https://api.openalex.org/works/https://doi.org/{DOI}?mailto={email}
```

### Ключевые поля ответа

| Поле | Описание |
|---|---|
| `title` | Название статьи |
| `doi` | Полный DOI (`https://doi.org/10.xxx/...`) |
| `publication_year` | Год публикации |
| `cited_by_count` | Количество цитирований |
| `type` | Тип работы (`article`, `review`, etc.) |
| `authorships[].author.display_name` | Имена авторов |
| `primary_location.source.display_name` | Название журнала |
| `primary_location.biblio.volume` | Том |
| `primary_location.biblio.first_page` / `last_page` | Страницы |

### HTTP-статусы

| Статус | Значение |
|---|---|
| 200 | Статья найдена → CONFIRMED |
| 404 | Статья не найдена → NOT_FOUND |
| 429 | Rate limit → повторить с паузой |
| 5xx | Ошибка сервера → ERROR |

---

## Формат выходного файла

Совместим с `crawl4ai/factcheck_crawl4ai.py` (можно парсить теми же скриптами):

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
OpenAlex Type        : article
```

**Поля:** `URL`, `FACT`, `EXPECT`, `DOI`, `STATUS` (CONFIRMED/ERROR/SKIP), `SUCCESS`, `ERROR` (опционально), `====...====`, метаданные OpenAlex.

---

## API скрипта (основные функции)

```python
from openalex.factcheck_openalex import extract_doi, lookup_doi

# Извлечь DOI из target
doi = extract_doi({"url": "https://doi.org/10.1136/bmj.n71", "expect": ""})
# → "10.1136/bmj.n71"

# Запросить OpenAlex
data, error = lookup_doi("10.1136/bmj.n71", timeout=15, mailto="me@example.com")
# data = {"title": "...", "publication_year": 2021, ...}
# error = None (или "NOT_FOUND" / "HTTP 429" / etc.)
```

---

## Сравнение OpenAlex vs другие источники

| Параметр | OpenAlex (Ур.0.5) | Crawl4AI (Ур.2) | researcher-web (Ур.1) |
|---|---|---|---|
| **Стоимость** | Бесплатно (CC0) | Бесплатно | Бесплатно (встроен) |
| **Скорость** | ~0.5-1 сек/DOI | ~5-30 сек/URL | ~3-10 сек/факт |
| **Надёжность** | API (структурированный JSON) | Парсинг HTML (может быть EMPTY) | Неструктурированный текст |
| **Метаданные** | ✅ Авторы, журнал, год, cited_by | ❌ Только сырой текст | ❌ Не всегда |
| **Ограничения** | Только DOI (не все статьи в индексе) | Любой URL | Любой запрос |
| **Когда использовать** | Первым делом для DOI | После OpenAlex, для контента | Базовые факты без DOI |

---

## Известные ограничения

1. **Не все DOI есть в OpenAlex** — некоторые статьи (особенно русскоязычные, свежие, из мелких журналов) могут отсутствовать. Решение: NOT_FOUND → Ур.1 (Crawl4AI).
2. **Нет полного текста** — OpenAlex даёт только метаданные, не содержимое статьи. Для контента → Ур.2 (Crawl4AI).
3. **Rate limit без mailto** — ~10k запросов/день. С `--mailto` → Polite Pool (100k/день).
4. **Не для всего** — только DOI. Для URL без DOI (gov.ru, who.int) → SKIP, сразу Ур.1.

---

## Связанные документы

- `../docs/knowledge.md` — полный протокол работы (каскад, .docx, техконстанты)
- `../docs/architecture.md` — архитектура конвейера редактуры
- `../playwright.md` — референс Playwright MCP (Ур.2.5, интерактивный браузер)
- `../scrapling/scrapling.md` — референс Scrapling (Ур.3)
- `../firecrawl/firecrawl.md` — референс FireCrawl (Ур.4 резерв)
- `../crawl4ai/factcheck_crawl4ai.py` — Crawl4AI (Ур.2)
- `factcheck_openalex.py` — **этот скрипт**
