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

# 2. Создать venv в КОРНЕ проекта и установить зависимости
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r pipeline/requirements.txt      # Windows
# .venv/bin/python -m pip install -r pipeline/requirements.txt            # Linux/Mac

# 3. Заполнить pipeline/targets.json ссылками для проверки
# 4. Запустить каскад фактчекинга (артефакты пишутся в workspace/)

.venv/Scripts/python.exe pipeline/openalex/factcheck_openalex.py --targets pipeline/targets.json --prefix oa --timeout 15
.venv/Scripts/python.exe pipeline/crawl4ai/factcheck_crawl4ai.py --targets pipeline/targets.json --prefix crawl --timeout 45
.venv/Scripts/python.exe pipeline/scrapling/factcheck_scrapling.py --targets pipeline/targets.json --prefix sc --timeout 90
firecrawl scrape 'https://...' -o workspace/firecrawl_<name>.md

# 5. (или) Авторежим — весь каскад одной командой (вместо ручного п.4):
.venv/Scripts/python.exe pipeline/sam.py --targets pipeline/targets.json
# .venv/bin/python pipeline/sam.py --targets pipeline/targets.json            # Linux/Mac
# Результат: workspace/sam_verdicts.json (вердикты по каждой цели) + workspace/sam_report.md
```
> Для Linux/Mac заменить `Scripts` на `bin`, а `python` на `python3` в путях к Python.
(При необходимости укажите `--out-dir`, чтобы записать результаты в другой каталог.)

Коды выхода `sam.py`: `0` — нет REFUTED; `1` — есть REFUTED (гейт остановился); `2` — ошибка конфигурации (targets не найден / пустой список). Уровни 1/4/5/6 программно недоступны (handoff), FireCrawl (Ур.4) автоматически не вызывается.

## Документация

| Файл | Назначение |
|------|-----------|
| [`docs/architecture.md`](pipeline/docs/architecture.md) | Архитектура конвейера — 5 ролей, 10 этапов, 7 принципов |
| [`docs/knowledge.md`](pipeline/docs/knowledge.md) | Каскад веб-фактчекинга — техконстанты, команды запуска |
| [`docs/cascade.md`](pipeline/docs/cascade.md) | Единый источник схемы каскада — 7 уровней, правила эскалации, словарь вердиктов |
| [`docs/docx-protocol.md`](pipeline/docs/docx-protocol.md) | Протокол правки .docx через python-docx — правила, шаблоны, антипаттерны |
| [`docs/llm.md`](pipeline/docs/llm.md) | Полное руководство по prompt engineering — техники, шаблоны, безопасность (Anthropic, OpenAI, Google, Meta, OWASP) |
| [`prompts/`](pipeline/prompts/) | Готовые шаблоны промптов для ролей конвейера — 5 заготовок (reviewer, textwriter, tech-executor, factchecker, co-orchestrator) |


## Структура проекта

```
├── README.md                         ← Этот файл
├── skills-lock.json                  ← Лок внешних навыков (hush-* — локально)
├── .gitignore / .editorconfig        ← Конфиги git и редактора
├── .venv/                            ← Виртуальное окружение (вне git)
├── workspace/                        ← Рантайм-артефакты (вне git)
│
├── .agents/                          ← Навыки и MCP-конфиг
│   ├── mcp.json.example              ← Шаблон MCP-серверов    │   └── skills/                       ← 3 навыка (docx, hush-docx,
    │                                       find-skills)
│
└── pipeline/                         ← Основной код конвейера
    ├── __init__.py                   ← Пакет
    ├── common.py                     ← Общие утилиты (prefix-валидация,
    │                                    чтение targets.json)
    ├── requirements.txt              ← Python-зависимости
    ├── targets.json                  ← Цели для проверки (заполняется
    │                                    перед запуском)

    ├── docs/                         ← Документация (5 файлов)
    │   ├── architecture.md           ← Архитектура конвейера
    │   ├── knowledge.md              ← Каскад фактчекинга
    │   ├── cascade.md                ← Единый источник схемы каскада
    │   ├── docx-protocol.md          ← Протокол правки .docx
    │   └── llm.md                    ← Prompt engineering (полное руководство)

    ├── openalex/                     ← Ур.0.5 — валидация DOI
    │   ├── factcheck_openalex.py     ← Скрипт: OpenAlex REST API
    │   └── openalex.md               ← Референс команд
    │
    ├── crawl4ai/                     ← Ур.2 — базовый HTTP-парсинг
    │   └── factcheck_crawl4ai.py     ← Скрипт: Crawl4AI
    │
    ├── scrapling/                    ← Ур.3 — обход Cloudflare
    │   ├── factcheck_scrapling.py    ← Скрипт: Scrapling StealthySession
    │   └── scrapling.md              ← Референс команд
    │
    └── firecrawl/                    ← Ур.4 — платный резерв
        └── firecrawl.md              ← Референс команд
```
