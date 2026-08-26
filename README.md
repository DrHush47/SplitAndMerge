# Split & Merge — конвейер редактуры + каскад фактчекинга

Гибридный конвейер для редактуры научных текстов по ГОСТ/журнальным стандартам
и автоматической верификации источников. Главная идея — не доверять LLM
без программной проверки.

**5 ролей** (Оркестратор, Рецензент, Текстовик, Технический исполнитель,
Факт-чекер) работают по модели split-and-merge: задача разделяется на
«творческие» и «механические» подзадачи, каждая идёт своему исполнителю,
результаты собираются и валидируются.

**10 этапов конвейера:** критический разбор → декомпозиция →
сбор фактов → генерация → повторная верификация → рецензирование →
сборка → механическая правка → программная вычитка → финальная проверка.

**8 уровней фактчекинга** — от бесплатного OpenAlex до платного FireCrawl
(только как резерв): ~95% проверок закрываются на бесплатных уровнях.

## Быстрый старт

```bash
# 1. Настроить MCP-конфиг
cp .agents/mcp.json.example .agents/mcp.json

# 2. Установить зависимости
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

> Для Linux/Mac заменить `Scripts` на `bin` в путях к Python.

## Документация

| Файл | Назначение |
|------|-----------|
| [`docs/architecture.md`](pipeline/docs/architecture.md) | Архитектура конвейера — 5 ролей, 10 этапов, 7 принципов |
| [`docs/knowledge.md`](pipeline/docs/knowledge.md) | Каскад веб-фактчекинга — 7 уровней, техконстанты, команды запуска |
| [`docs/docx-protocol.md`](pipeline/docs/docx-protocol.md) | Протокол правки .docx через python-docx — правила, шаблоны, антипаттерны |
| [`docs/results.md`](pipeline/docs/results.md) | Шаблон отчёта факт-чекера |
| [`hush-prompt`](.agents/skills/hush-prompt/SKILL.md) | Prompt engineering — правила и шаблоны для LLM-промптов (заменил удалённый `docs/llm.md`) |


## Структура проекта

```
├── README.md                         ← Этот файл
├── skills-lock.json                  ← Лок установленных навыков
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

    ├── docs/                         ← Документация (4 файла)
    │   ├── architecture.md           ← Архитектура конвейера
    │   ├── knowledge.md              ← Каскад фактчекинга
    │   ├── docx-protocol.md          ← Протокол правки .docx
    │   └── results.md                ← Шаблон отчёта

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
