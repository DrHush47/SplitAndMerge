# Split & Merge — конвейер редактуры + каскад фактчекинга

[![CI](https://github.com/DrHush47/SplitAndMerge/actions/workflows/ci.yml/badge.svg)](https://github.com/DrHush47/SplitAndMerge/actions/workflows/ci.yml)

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

**7 уровней фактчекинга** — схема, эскалация, вердикты только в [`pipeline/docs/cascade.md`](pipeline/docs/cascade.md): ~95% проверок закрываются на бесплатных уровнях.

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

Коды выхода `sam.py`: `0` — нет REFUTED; `1` — есть REFUTED; `2` — ошибка конфигурации. Правила эскалации и handoff-уровни — только в [`pipeline/docs/cascade.md`](pipeline/docs/cascade.md). Для работы фазы 3 (Scrapling) всегда включайте уровень 2 в `--levels` (иначе фазе 3 не из чего эскалироваться).

### Быстрый режим фактчекинга (без зависимостей)

> Workflow, конвенция имён, дефект DOI-сверки — только в [`pipeline/manual/manual.md`](pipeline/manual/manual.md), здесь не дублируются.

### Установка и команда `sam` (рекомендуемый способ)

```bash
# 1. Установить пакет в venv (базовая установка — лёгкая, без тяжёлых зависимостей)
.venv/Scripts/python.exe -m pip install -e .
# .venv/bin/python -m pip install -e .                                # Linux/Mac

# 2. Полный набор (веб-краулеры + python-docx) — если нужен весь каскад:
# .venv/Scripts/python.exe -m pip install -e ".[web,docx]"

# 3. Запуск авто-каскада одной командой:
sam --targets pipeline/targets.json --out-dir workspace --levels 0.5,2,3
```

Команда `sam` устанавливается в venv и доступна из любого каталога. Запуск через
`python pipeline/sam.py` (см. «Быстрый старт», п. 5) — равноправная альтернатива
без установки пакета.

## Документация

| Файл | Назначение |
|------|-----------|
| [`docs/architecture.md`](pipeline/docs/architecture.md) | Архитектура конвейера — 5 ролей, 10 этапов, 7 принципов |
| [`docs/knowledge.md`](pipeline/docs/knowledge.md) | Каскад веб-фактчекинга — техконстанты, команды запуска |
| [`docs/cascade.md`](pipeline/docs/cascade.md) | Единый источник схемы каскада — 7 уровней, правила эскалации, словарь вердиктов |
| [`docs/docx-protocol.md`](pipeline/docs/docx-protocol.md) | Протокол правки .docx через python-docx — правила, шаблоны, антипаттерны |
| [`docs/llm.md`](pipeline/docs/llm.md) | Полное руководство по prompt engineering — техники, шаблоны, безопасность (Anthropic, OpenAI, Google, Meta, OWASP). **Рекомендован рецензенту и (со-)оркестратору для удобного написания промптов** |
| [`pipeline/manual/manual.md`](pipeline/manual/manual.md) | Быстрый режим фактчекинга без зависимостей — workflow, конвенция имён, референс сканера |
| [`prompts/`](pipeline/prompts/) | Готовые шаблоны промптов для ролей конвейера — 5 заготовок (reviewer, textwriter, tech-executor, factchecker, co-orchestrator). Для роли текстовика оптимален [Writing Editor (Gemini Gem)](https://gemini.google.com/gem/writing-editor) (см. [`prompts/textwriter.md`](pipeline/prompts/textwriter.md) § Первоисточники) |

### Карта чтения

Порядок чтения: `pipeline/docs/architecture.md` → `pipeline/docs/cascade.md` → `pipeline/docs/knowledge.md` §0.1 → нужный раздел (`pipeline/docs/docx-protocol.md` для правки .docx; `pipeline/manual/manual.md` для быстрого режима; `pipeline/prompts/` для текста роли; референс уровня `openalex/scrapling/firecrawl` только перед его запуском; **`pipeline/docs/llm.md` — рецензенту и (со-)оркестратору перед написанием промптов**; для роли текстовика оптимален [Writing Editor (Gemini Gem)](https://gemini.google.com/gem/writing-editor) — см. [`pipeline/prompts/textwriter.md`](pipeline/prompts/textwriter.md) § Первоисточники).

Каноны (не дублируются в других файлах): схема и вердикты — `cascade.md`; команды и пути — `knowledge.md` §0.1; код шаблона .docx — `pipeline/templates/docx_orchestrator.py`.

## Структура проекта

```
├── README.md                         ← Этот файл
├── pyproject.toml                    ← Пакет проекта: установка и команда `sam`
├── skills-lock.json                  ← Лок внешних навыков (hush-* — локально)
├── .gitignore / .editorconfig        ← Конфиги git и редактора
├── .venv/                            ← Виртуальное окружение (вне git)
├── workspace/                        ← Рантайм-артефакты (вне git)
├── tests/                            ← pytest-набор тестового ядра (вне установки)
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

    ├── prompts/                      ← Шаблоны ролей (5 заготовок-промптов)
    ├── templates/                    ← Журнал этапов (progress.template.md)

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
    ├── manual/                       ← Быстрый режим (Ур.1→Ур.5) — без зависимостей
    │   ├── factcheck_manual.py       ← Сканер ручных источников (stdlib-only)
    │   └── manual.md                 ← Референс режима
    │
    └── firecrawl/                    ← Ур.4 — платный резерв
        └── firecrawl.md              ← Референс команд
```
