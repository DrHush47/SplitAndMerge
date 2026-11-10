# AGENTS.md — Манифест и маршрутизация для ИИ-агентов

> Входная точка проекта **Split & Merge** (конвейер редактуры научных текстов + 7-уровневый каскад фактчекинга).
> Полная документация для человека: [`README.md`](README.md).

---

## 1. Базовые правила и среда (Guardrails)

- **Python / Venv:** всегда запускать через `.venv/Scripts/python.exe` (Windows) или `.venv/bin/python` (Linux/Mac).
- **Кодировка (Windows):** в начале каждого Python-скрипта принудительно ставить UTF-8 на `stdout`/`stderr` (`sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')`), чтобы не падать на `cp1251`.
- **Изоляция артефактов:** все рабочие файлы, выгрузки, черновики и результаты сессий создавать и хранить **строго внутри `workspace/<подпапка>/`** (вне git). Корень проекта не засорять.
- **Нулевая толерантность к галлюцинациям:** категорически запрещено выдумывать библиографические ссылки, DOI, фамилии авторов, численные данные или синтетические URL. Работа только по верифицированному сырью.
- **Синхронизация с GitHub:** после завершённого смыслового изменения в проекте (или по запросу) запускать `& "C:\Program Files\Git\bin\bash.exe" sync.sh "<описание>"` (на Windows вызывать именно Git Bash, а не системный WSL `bash`).

---

## 2. Маршрутизация контекста (SSOT — что читать под задачу)

Не читай все файлы подряд — открывай только профильный канон под текущую задачу:

| Задача / Модуль | Канонический документ (SSOT) | Инструмент / Скрипт / Навык |
|---|---|---|
| **Общая архитектура и этапы** | [`pipeline/docs/architecture.md`](pipeline/docs/architecture.md) | 5 ролей, 10 этапов split-and-merge |
| **Схема и уровни фактчекинга** | [`pipeline/docs/cascade.md`](pipeline/docs/cascade.md) | `sam` / `pipeline/sam.py`, вердикты в `pipeline/verdicts.py` |
| **Команды и техконстанты каскада** | [`pipeline/docs/knowledge.md`](pipeline/docs/knowledge.md) | `factcheck_openalex.py` (0.5), `crawl4ai` (2), `scrapling` (3), `firecrawl` (4) |
| **Быстрый фактчекинг (stdlib)** | [`pipeline/manual/manual.md`](pipeline/manual/manual.md) | `pipeline/manual/factcheck_manual.py` (Ур. 1 → Ур. 5 без зависимостей) |
| **Биомедицинский фактчекинг** | [`pipeline/docs/biomed-protocol.md`](pipeline/docs/biomed-protocol.md) | `pipeline/biomed/factcheck_biomed.py` (Ур. 0.7) + навыки в `.agents/skills/` |
| **Правка и генерация `.docx`** | [`pipeline/docs/docx-protocol.md`](pipeline/docs/docx-protocol.md) | `python-docx`, шаблон [`pipeline/templates/docx_orchestrator.py`](pipeline/templates/docx_orchestrator.py), навык `hush-docx` |
| **Сборка презентаций `.pptx`** | [`pipeline/docs/presentation-protocol.md`](pipeline/docs/presentation-protocol.md) | `python-pptx`, триада доклада, `fit_in_box`, экспорт 1080p |
| **Исследовательские навыки** | [`pipeline/docs/research-skills.md`](pipeline/docs/research-skills.md) | `.agents/skills/`: `deep-research`, `litreview`, `deepread`, `research`, `research-summarizer` |
| **Написание промптов (PE)** | [`pipeline/docs/llm.md`](pipeline/docs/llm.md) | Ролевые заготовки в [`pipeline/prompts/`](pipeline/prompts/) |

---

## 3. Роли конвейера и шаблоны промптов (`pipeline/prompts/`)

1. **Оркестратор / Со-оркестратор** ([`co-orchestrator.md`](pipeline/prompts/co-orchestrator.md)) — декомпозиция задачи, ведение журнала прогресса ([`progress.template.md`](pipeline/templates/progress.template.md)), сборка промптов.
2. **Рецензент** ([`reviewer.md`](pipeline/prompts/reviewer.md)) — критический разбор исходника, сверка с требованиями журнала/ГОСТ, финальный аудит.
3. **Факт-чекер** ([`factchecker.md`](pipeline/prompts/factchecker.md)) — программная валидация источников по каскаду (OpenAlex, Crossref, PubMed/Europe PMC, краулеры).
4. **Текстовик** ([`textwriter.md`](pipeline/prompts/textwriter.md)) — генерация текстовых блоков `[TEXT-N]` строго по валидированной базе (оптимально: **Writing Editor GemBot** → **Claude** для академической хуманизации; 2 строгих режима оформления References без смешивания).
5. **Технический исполнитель** ([`tech-executor.md`](pipeline/prompts/tech-executor.md)) — механическое внесение правок в `.docx`/`.pptx` одним скриптом с post-check проверкой.
