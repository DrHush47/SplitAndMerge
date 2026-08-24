# Pipeline — конвейер редактуры + каскад фактчекинга

Многоагентная система для редактуры научных текстов и верификации источников.

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
| [`docs/knowledge.md`](pipeline/docs/knowledge.md) | Каскад веб-фактчекинга — 8 уровней, техконстанты, команды запуска |
| [`docs/docx-protocol.md`](pipeline/docs/docx-protocol.md) | Протокол правки .docx — правила, шаблоны, антипаттерны |
| [`docs/architecture.md`](pipeline/docs/architecture.md) | Архитектура конвейера — роли, этапы, принципы |
| [`docs/notes.md`](pipeline/docs/notes.md) | Идеи, находки, MCP-серверы, инструменты |

## Структура проекта

```
pipeline/
├── docs/                  ← Документация
├── crawl4ai/              ← Crawl4AI (Ур.2: базовый HTTP-парсинг)
├── openalex/              ← OpenAlex API (Ур.0.5: валидация DOI)
├── scrapling/             ← Scrapling (Ур.3: обход Cloudflare)
├── firecrawl/             ← FireCrawl (Ур.4: платный резерв)
├── common.py              ← Общие утилиты (prefix-валидация, чтение targets)
├── requirements.txt       ← Python-зависимости
└── targets.json           ← Цели для проверки (заполняется перед запуском)
```
