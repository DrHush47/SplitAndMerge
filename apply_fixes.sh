#!/usr/bin/env bash
# =============================================================================
# apply_fixes.sh — применяет 7 правок рецензентского ревью к репо SplitAndMerge
#
# Что делает:
#   1. Проверяет, что запущен из корня репо и дерево пригодно для правки
#   2. Делает резервную копию изменяемых файлов ВНЕ репо (соседняя папка)
#   3. Записывает исправленные версии трёх файлов (зашиты в этот скрипт)
#   4. Удаляет осиротевший pipeline/docs/llm.md
#   5. Программно верифицирует каждую из правок (PASS/FAIL)
#
# После успешного прогона запусти синхронизатор:
#   bash sync.sh "fix: 7 issues из ревью — см. apply_fixes.sh"
#
# Повторный запуск безопасен: скрипт увидит уже применённые правки и выйдет.
# Откат: содержимое папки бэкапа вернуть назад, а llm.md —
#   git checkout HEAD -- pipeline/docs/llm.md
# =============================================================================

# Защита от запуска через sh/dash (нужен bash из-за <(...) и [[ ]])
if [ -z "${BASH_VERSION:-}" ]; then
    exec bash "$0" "$@"
fi

BAKDIRNAME="SplitAndMerge_backup_$(date +%Y%m%d_%H%M%S)"

say()  { printf '%s\n' "$*"; }
pass=0; fail=0
ok()   { pass=$((pass+1)); printf '  [PASS] %s\n' "$1"; }
bad()  { fail=$((fail+1)); printf '  [FAIL] %s\n' "$1"; }

# --- Шаг 1: окружение -------------------------------------------------------
cd "$(dirname "$0")" || { say "Не могу перейти в папку скрипта."; exit 1; }

say "=== apply_fixes.sh: правки ревью SplitAndMerge ==="
echo ""

if [ ! -d .git ] || [ ! -f README.md ] || [ ! -d pipeline ]; then
    say "ОШИБКА: это не корень репо SplitAndMerge."
    say "Положи скрипт в корень репо (рядом с README.md и sync.sh) и повтори."
    exit 1
fi

command -v git >/dev/null 2>&1 || { say "ОШИБКА: git не найден в PATH."; exit 1; }

# Уже применено ранее?
MARKERS=0
grep -qF '7 уровней фактчекинга' README.md                 && MARKERS=$((MARKERS+1))
[ ! -f pipeline/docs/llm.md ]                              && MARKERS=$((MARKERS+1))
grep -qF 'python -m venv pipeline/crawl4ai/.venv' README.md && MARKERS=$((MARKERS+1))
grep -qF '# Scrapling — Ур.3 каскада факт-чекинга' pipeline/scrapling/scrapling.md && MARKERS=$((MARKERS+1))
grep -qF '"id": "ref01", "url": "https://doi.org/10.1038/s41591-018-0300-7"' \
     pipeline/openalex/openalex.md                          && MARKERS=$((MARKERS+1))

if [ "$MARKERS" -ge 4 ]; then
    MOD=$(git status --porcelain | grep -Ev '^\?\?' || true)
    if [ -n "$MOD" ]; then
        say "Похоже, правки уже применены и ожидают коммита (маркеров: $MARKERS/5)."
        say "Запусти синхронизатор: bash sync.sh"
        exit 0
    fi
fi

# Грязное дерево (изменённые/удалённые отслеживаемые файлы) — опасно перезаписывать
MODIFIED=$(git status --porcelain | grep -Ev '^\?\?' || true)
if [ -n "$MODIFIED" ] && [ "${1:-}" != "--force" ]; then
    say "ОШИБКА: в репо есть незакоммиченные изменения:"
    echo "$MODIFIED"
    echo ""
    say "Сначала закоммить их (bash sync.sh) или спрячь (git stash),"
    say "либо запусти принудительно: bash apply_fixes.sh --force"
    exit 1
fi

# --- Шаг 2: бэкап вне репо (чтобы sync.sh его не запушил) -------------------
BAKDIR="$(dirname "$PWD")/$BAKDIRNAME"
mkdir -p "$BAKDIR" || { say "ОШИБКА: не создать папку бэкапа."; exit 1; }
for f in README.md pipeline/scrapling/scrapling.md pipeline/openalex/openalex.md; do
    cp "$f" "$BAKDIR/$(echo "$f" | tr '/' '_').bak"
done
cp pipeline/docs/llm.md "$BAKDIR/pipeline_docs_llm.md.bak" 2>/dev/null
say "Бэкап: $BAKDIR"
echo ""

# --- Шаг 3: запись исправленных файлов --------------------------------------
say "Записываю исправленные файлы..."
cat > "README.md" << 'SPLITMERGE_EOF_1'
# Split & Merge — конвейер редактуры + каскад фактчекинга

Гибридный конвейер для редактуры научных текстов по ГОСТ/журнальным стандартам
и автоматической верификации источников. Главная идея — не доверять LLM
без программной проверки.

**5 ролей** (Оркестратор, Рецензент, Текстовик, Технический исполнитель,
Факт-чекер) работают по модели split-and-merge: задача разделяется на
«творческие» и «механические» подзадачи, каждая идёт своему исполнителю,
результаты собираются и валидируются.

**10 этапов конвейера** (плюс промежуточная верификация 4.5):
критический разбор → декомпозиция → сбор фактов → генерация →
повторная верификация → рецензирование → сборка промпта →
механическая правка → программная вычитка → точечные правки →
финальная проверка.

**7 уровней фактчекинга** — от бесплатного OpenAlex до платного FireCrawl
(только как резерв): ~95% проверок закрываются на бесплатных уровнях.

## Быстрый старт

```bash
# 1. Настроить MCP-конфиг
cp .agents/mcp.json.example .agents/mcp.json

# 2. Создать venv (.venv не хранится в репо) и установить зависимости
python -m venv pipeline/crawl4ai/.venv
./pipeline/crawl4ai/.venv/Scripts/python.exe -m pip install -r pipeline/requirements.txt

# 3. Заполнить targets.json ссылками для проверки
# 4. Запустить каскад фактчекинга

# OpenAlex (Ур.0.5 — проверка DOI):
./pipeline/crawl4ai/.venv/Scripts/python.exe pipeline/openalex/factcheck_openalex.py --targets pipeline/targets.json --prefix oa --timeout 15

# Crawl4AI (Ур.2 — базовый парсинг):
./pipeline/crawl4ai/.venv/Scripts/python.exe pipeline/crawl4ai/factcheck_crawl4ai.py --targets pipeline/targets.json --prefix crawl --timeout 45

# Scrapling (Ур.3 — обход Cloudflare):
./pipeline/crawl4ai/.venv/Scripts/python.exe pipeline/scrapling/factcheck_scrapling.py --targets pipeline/targets.json --prefix sc --timeout 90

# FireCrawl (Ур.4 — платный резерв):
firecrawl scrape 'https://...' -o pipeline/firecrawl/.firecrawl/<name>.md
```

> Для Linux/Mac заменить `Scripts` на `bin`, а `python` на `python3` в путях к Python.

## Документация

| Файл | Назначение |
|------|-----------|
| [`docs/architecture.md`](pipeline/docs/architecture.md) | Архитектура конвейера — 5 ролей, 10 этапов, 7 принципов |
| [`docs/knowledge.md`](pipeline/docs/knowledge.md) | Каскад веб-фактчекинга — 7 уровней, техконстанты, команды запуска |
| [`docs/docx-protocol.md`](pipeline/docs/docx-protocol.md) | Протокол правки .docx через python-docx — правила, шаблоны, антипаттерны |
| [`hush-prompt`](.agents/skills/hush-prompt/SKILL.md) | Prompt engineering — правила и шаблоны для LLM-промптов (заменил удалённый `docs/llm.md`) |


## Структура проекта

```
├── README.md                         ← Этот файл
├── skills-lock.json                  ← Лок внешних навыков (hush-* — локально)
├── .gitignore / .editorconfig        ← Конфиги git и редактора
│
├── .agents/                          ← Навыки и MCP-конфиг
│   ├── mcp.json.example              ← Шаблон MCP-серверов
│   └── skills/                       ← 4 навыка (docx, hush-docx,
│                                       hush-prompt, find-skills)
│
└── pipeline/                         ← Основной код конвейера
    ├── __init__.py                   ← Пакет
    ├── common.py                     ← Общие утилиты (prefix-валидация,
    │                                    чтение targets.json)
    ├── requirements.txt              ← Python-зависимости
    ├── targets.json                  ← Цели для проверки (заполняется
    │                                    перед запуском)

    ├── docs/                         ← Документация (3 файла)
    │   ├── architecture.md           ← Архитектура конвейера
    │   ├── knowledge.md              ← Каскад фактчекинга
    │   └── docx-protocol.md          ← Протокол правки .docx

    ├── openalex/                     ← Ур.0.5 — валидация DOI
    │   ├── factcheck_openalex.py     ← Скрипт: OpenAlex REST API
    │   └── openalex.md               ← Референс команд
    │
    ├── crawl4ai/                     ← Ур.2 — базовый HTTP-парсинг
    │   ├── factcheck_crawl4ai.py     ← Скрипт: Crawl4AI
    │   └── .venv/                    ← Виртуальное окружение
    │
    ├── scrapling/                    ← Ур.3 — обход Cloudflare
    │   ├── factcheck_scrapling.py    ← Скрипт: Scrapling StealthySession
    │   └── scrapling.md              ← Референс команд
    │
    └── firecrawl/                    ← Ур.4 — платный резерв
        ├── firecrawl.md              ← Референс команд
        ├── .gitignore                ← Исключает output из git
        └── .firecrawl/               ← Выходные файлы FireCrawl
```
SPLITMERGE_EOF_1

cat > "pipeline/scrapling/scrapling.md" << 'SPLITMERGE_EOF_2'
# Scrapling — Ур.3 каскада факт-чекинга

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

## Связанные документы

- `../docs/knowledge.md` — полный протокол работы (каскад, .docx, техконстанты)
- `../docs/architecture.md` — архитектура конвейера редактуры
- `../openalex/openalex.md` — референс OpenAlex (Ур.0.5, программная валидация DOI)
- `../firecrawl/firecrawl.md` — референс FireCrawl (Ур.4 резерв)
- `../crawl4ai/factcheck_crawl4ai.py` — Crawl4AI (Ур.2)
- `factcheck_scrapling.py` — **этот скрипт**
SPLITMERGE_EOF_2

cat > "pipeline/openalex/openalex.md" << 'SPLITMERGE_EOF_3'
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
  {"id": "ref01", "url": "https://doi.org/10.1038/s41591-018-0300-7", "fact": "Topol E.J. ...", "expect": "DOI 10.1038/s41591-018-0300-7"},
  {"id": "ref02", "url": "https://www.nature.com/articles/s41591-018-0300-7", "fact": "...", "expect": "DOI 10.1038/s41591-018-0300-7"}
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
- `../scrapling/scrapling.md` — референс Scrapling (Ур.3)
- `../firecrawl/firecrawl.md` — референс FireCrawl (Ур.4 резерв)
- `../crawl4ai/factcheck_crawl4ai.py` — Crawl4AI (Ур.2)
- `factcheck_openalex.py` — **этот скрипт**
SPLITMERGE_EOF_3


# --- Шаг 4: удаление осиротевшего llm.md ------------------------------------
say ""
say "Удаляю pipeline/docs/llm.md (осиротевший дубль hush-prompt)..."
rm -f pipeline/docs/llm.md

# --- Шаг 5: программная верификация -----------------------------------------
say ""
say "Верификация правок:"
echo ""

grep -qF  '7 уровней фактчекинга' README.md                  && ok  "C1  README: счётчик каскада теперь '7 уровней'"
grep -qF '8 уровней фактчекинга' README.md                   && bad "C1  README: осталось старое '8 уровней'" || true
grep -qF 'python -m venv pipeline/crawl4ai/.venv' README.md  && ok  "C3  README: шаг создания venv добавлен"
grep -qF 'Создать venv (.venv не хранится в репо)' README.md && ok  "C3  README: пометка про отсутствие .venv в репо"
grep -qF 'на `python3` в путях к Python' README.md           && ok  "C3  README: примечание про python3 для Linux/Mac"
[ ! -f pipeline/docs/llm.md ]                                && ok  "C2  docs/llm.md удалён"
grep -qF '# Scrapling — Ур.3 каскада факт-чекинга' pipeline/scrapling/scrapling.md && ok  "M1  scrapling.md: заголовок без дубля"
grep -qF '(Scrapling)' <(head -1 pipeline/scrapling/scrapling.md) 2>/dev/null && bad "M1  scrapling.md: дубль всё ещё в заголовке" || true
grep -qF '"id": "ref01", "url": "https://doi.org/10.1038/s41591-018-0300-7"' pipeline/openalex/openalex.md && ok  "M2  openalex.md: ref01 DOI консистентен"
N301=$(grep -cF 's41591-018-0301-7' pipeline/openalex/openalex.md 2>/dev/null)
N301=${N301:-0}
[ "$N301" -eq 0 ] 2>/dev/null && ok "M2  openalex.md: конфликтных DOI (...0301-7) не осталось" || bad "M2  openalex.md: найдены остатки DOI ...0301-7"
grep -qF 'Лок внешних навыков' README.md                     && ok  "M3  README: аннотация skills-lock.json уточнена"
grep -qF 'точечные правки' README.md                         && ok  "M4  README: чейн этапов дополнен точечными правками"
grep -qF 'промежуточная верификация 4.5' README.md           && ok  "M4  README: упомянут Этап 4.5"

echo ""
say "Итого: PASS=$pass FAIL=$fail"
echo ""

if [ "$fail" -gt 0 ]; then
    say "ЕСТЬ НЕУСПЕШНЫЕ ПРОВЕРКИ. Вернуть состояние можно так:"
    say "  cp \"$BAKDIR\"/*.bak  на исходные места (имена папок закодированы через _)"
    say "  git checkout HEAD -- pipeline/docs/llm.md"
    exit 1
fi

say "Все правки применены. Следующий шаг — отправить в GitHub:"
say "  bash sync.sh \"fix: 7 issues из ревью (уровни каскада, venv, удалён llm.md, заголовки, DOI)\""
exit 0
