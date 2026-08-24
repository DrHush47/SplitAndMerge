# Scrapling (Scrapling) — Ур.3 каскада факт-чекинга

> **Standalone-референс для агента.** В новой сессии без контекста — читай этот документ.
> **Основной инструмент:** `scrapling/factcheck_scrapling.py`
> **Пути:** относительно папки `pipeline/`. Для запуска из корня проекта — `./pipeline/crawl4ai/.venv/...` (см. `../docs/knowledge.md` §0.1).
> **Вендор:** [github.com/D4Vinci/Scrapling](https://github.com/D4Vinci/Scrapling) v0.4.11
> **Лицензия:** BSD-3-Clause

## Роль в каскаде

```
Ур.0.5 → OpenAlex API           (мгновенная проверка DOI)
Ур.1   → researcher-web         (поиск фактов)
Ур.2   → Crawl4AI               (базовый HTTP-парсинг)
Ур.2.5 → Playwright MCP         (интерактивный браузер, KEYLESS)
Ур.3   → Scrapling StealthySession  ← ТЫ ЗДЕСЬ (бесплатно, обход Cloudflare)
Ур.4   → FireCrawl              (резерв, платный)
Ур.5   → Человек                (ручная верификация)
Ур.6   → Gemini DeepSearch      (опционально)
```

**Когда применять Scrapling:**
- Crawl4AI (Ур.2) вернул EMPTY / Cloudflare-маркер / TIMEOUT
- Сайт с известной anti-bot защитой (Cloudflare Turnstile, DataDome)
- Пере-парсинг URL с изменившейся структурой (`--adaptive`)

**Когда НЕ применять:**
- Простые статические URL → используй Crawl4AI (быстрее в 10-50×)
- Если Scrapling не справился → передать на Ур.4 (FireCrawl)

---

## Quick start

```bash
# Windows
./crawl4ai/.venv/Scripts/python.exe scrapling/factcheck_scrapling.py --targets targets.json --prefix sc --timeout 90

# Linux/Mac
./crawl4ai/.venv/bin/python scrapling/factcheck_scrapling.py --targets targets.json --prefix sc --timeout 90
```

Результат: `scrapling/sc_{id}.txt` для каждого URL.

---

## Формат targets.json

```json
[
  {"id": "ref01", "url": "https://example.com/article", "fact": "Article exists"},
  {"id": "ref02", "url": "https://journal.org/paper", "fact": "DOI exists", "expect": "10.1000/xyz123"}
]
```

**Обязательные поля:** `id`, `fact`, `url`
**Опциональные:** `expect` (ожидаемое значение)

---

## CLI-аргументы

| Аргумент | По умолч. | Описание |
|---|---|---|
| `--targets` | (required) | Путь к JSON-файлу с целями |
| `--prefix` | `sc` | Префикс выходных файлов |
| `--timeout` | `90` | Таймаут на URL в **секундах** (конвертится в ms внутри) |
| `--adaptive` | `false` | Включить adaptive-парсинг (для сайтов с меняющейся структурой) |
| `--css-selector` | `null` | CSS-селектор для извлечения конкретного контента (например, `.article-body`) |
| `--no-cloudflare` | `false` | Отключить решение Cloudflare (быстрее для простых сайтов) |

---

## Технические константы

| Параметр | Значение |
|---|---|
| **venv** | `./crawl4ai/.venv/Scripts/python.exe` (Windows) / `./crawl4ai/.venv/bin/python` (Linux/Mac) |
| **Скрипт** | `scrapling/factcheck_scrapling.py` |
| **Выходные файлы** | `scrapling/{prefix}_{id}.txt` |
| **Таймаут** | `--timeout` в секундах → `* 1000` для Playwright (ms) |
| **Браузеры** | `%USERPROFILE%\AppData\Local\ms-playwright\` (Windows) |
| **Стоимость** | Бесплатно (локальный Playwright) |

---

## API Scrapling (проверено на v0.4.11)

### Что работает

| Метод | Результат | Приоритет в `extract_text()` |
|---|---|---|
| `page.get_all_text()` | ✅ Plain text | 1 (BEST) |
| `str(page.html_content)` | ✅ Полный HTML | 2 (fallback) |
| `page.body.decode('utf-8')` | ✅ Raw bytes → строка | 3 (fallback) |
| `page.status` | ✅ HTTP-статус | — |
| `page.css('.sel', adaptive=True)` | ✅ Adaptive CSS | — |

### DOM-парсинг через selectolax

Scrapling использует `selectolax` (быстрее BeautifulSoup) для разбора HTML.
Доступны методы элемента:

| Метод | Назначение | Пример |
|-------|-----------|--------|
| `page.find(selector)` | Первый matching элемент | `page.find("h1")` |
| `page.find_all(selector)` | Все matching элементы | `page.find_all("a")` |
| `el.attributes` | Словарь атрибутов | `el.attributes.get("href")` |
| `el.get(attr)` | Конкретный атрибут | `el.get("src")` |
| `el.matches(selector)` | Проверить совпадение | `el.matches(".active")` |

> **Примечание:** Для фактчекинга мы извлекаем весь текст через `extract_text()`. DOM-парсинг полезен для точечного извлечения метаданных (заголовки, авторы, даты) без парсинга всего контента.

### Что НЕ работает

| Метод | Проблема |
|---|---|
| `page.markdown` | ❌ **Не существует** (в отличие от Crawl4AI) |
| `page.text` | ❌ `TextHandler`, `str()` возвращает пустую строку |
| `page.text.clean()` / `.extract()` | ❌ Возвращают пустоту |
| `page.content` | ❌ **Не существует** (используй `html_content`) |

### StealthySession — важные детали

- **Синхронный** (`with StealthySession(...)` — не `async with`)
- Держит браузер открытым между запросами → 10-20× быстрее one-off
- `session.fetch(url, timeout=ms, network_idle=True)` — timeout в миллисекундах
- Playwright может кидать свой `TimeoutError` (не наследует `builtins.TimeoutError`) — скрипт ловит через `except Exception` с проверкой имени

### extract_text() — безопасное извлечение (reimplement при необходимости)

```python
def extract_text(page):
    """Безопасное извлечение текста — get_all_text → html_content → body.decode."""
    try:
        t = page.get_all_text()
        if t is not None and str(t).strip():
            return str(t), 'text'
    except Exception:
        pass
    try:
        t = str(page.html_content)
        if t and len(t) > 100:
            return t, 'html'
    except Exception:
        pass
    try:
        t = page.body.decode('utf-8', errors='replace')
        if t.strip():
            return t, 'body'
    except Exception:
        return '', 'empty'
```

---

## Формат выходного файла

Совместим с `crawl4ai/factcheck_crawl4ai.py` (можно парсить теми же скриптами):

```
URL: https://example.com/article
FACT: Article exists
EXPECT: 
SUCCESS: True
EXTRACTOR: text
STATUS: 200

======================================================================
<текст страницы>
```

**Поля:** `URL`, `FACT`, `EXPECT`, `SUCCESS`, `EXTRACTOR`, `STATUS`, `ERROR` (опционально), `====...====`, текст.

---

## Примеры

### Базовый запуск
```bash
./crawl4ai/.venv/Scripts/python.exe scrapling/factcheck_scrapling.py \
  --targets targets.json --prefix sc --timeout 90
```

### Adaptive-парсинг с CSS-селектором
```bash
./crawl4ai/.venv/Scripts/python.exe scrapling/factcheck_scrapling.py \
  --targets targets_retry.json --prefix sc2 \
  --adaptive --css-selector "body"
```

### Без Cloudflare (быстрее)
```bash
./crawl4ai/.venv/Scripts/python.exe scrapling/factcheck_scrapling.py \
  --targets targets.json --prefix sc_fast --timeout 30 --no-cloudflare
```

---

## Сравнение Scrapling vs FireCrawl

| Параметр | Scrapling (Ур.3) | FireCrawl (Ур.4) |
|---|---|---|
| **Стоимость** | Бесплатно | Платные кредиты |
| **Cloudflare bypass** | ✅ StealthySession | ✅ |
| **page.markdown** | ❌ Нет | ✅ Есть |
| **Скорость (batch)** | ~1-2 сек/URL | ~3-5 сек/URL |
| **CLI** | Python-скрипт | `firecrawl scrape` |
| **JS-рендеринг** | ✅ Playwright | ✅ |
| **Когда использовать** | Первым, после Crawl4AI | Fallback, если Scrapling не справился |

---

## Известные ограничения

1. **Cloudflare-URL могут зависать** — если сайт с активной Cloudflare-защитой, `network_idle=True` может ждать вечно. Решение: использовать `--timeout` (по умолч. 90 сек).
2. **Нет `page.markdown`** — если нужен markdown, используй FireCrawl (Ур.4) или CLI Scrapling: `scrapling extract stealthy-fetch 'url' out.md`
3. **Один браузер на batch** — `StealthySession` держит один экземпляр Chromium. Для 30+ URL может быть медленнее, чем параллельные запросы.
4. **Playwright на Windows** — требует совместимости с антивирусом (изредка блокирует бинарники).

---

### Playwright MCP как companion-инструмент

Scrapling использует Playwright Chromium под капотом. Для **интерактивных** задач (логин, формы, скриншоты) используй отдельный **Playwright MCP** (Ур.2.5 каскада) — см. полный референс в [`playwright.md`](../playwright.md).

Общий движок: оба инструмента используют один `ms-playwright` Chromium (1.6 GB), дополнительное место на диске: 0 байт.

---

## Связанные документы

- `../docs/knowledge.md` — полный протокол работы (каскад, .docx, техконстанты)
- `../docs/architecture.md` — архитектура конвейера редактуры
- `../openalex/openalex.md` — референс OpenAlex (Ур.0.5, программная валидация DOI)
- `../playwright.md` — референс Playwright MCP (Ур.2.5, интерактивный браузер — общий Chromium)
- `../firecrawl/firecrawl.md` — референс FireCrawl (Ур.4 резерв)
- `../crawl4ai/factcheck_crawl4ai.py` — Crawl4AI (Ур.2)
- `factcheck_scrapling.py` — **этот скрипт**
