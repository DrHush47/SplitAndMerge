# AGENTS.md — Единая точка входа и маршрутизация для ИИ-агентов

> **Главная точка старта проекта Split & Merge (v2 — Agent-First Core).**
> Документация для человека: [`README.md`](README.md). Полная схема ядра: [`pipeline/docs/architecture.md`](pipeline/docs/architecture.md).

---

## 1. Базовые правила и среда (Guardrails)

- **Python / Venv:** всегда запускать через `.venv/Scripts/python.exe` (Windows) или `.venv/bin/python` (Linux/Mac).
- **Лёгкий профиль по умолчанию и подтверждение доустановки:** штатная база — профиль `lite` ([`pipeline/requirements-lite.txt`](pipeline/requirements-lite.txt) / `pip install -e ".[lite]"`, ~16,5 МБ, без браузеров; закрывает ~95% задач). Перед доустановкой **любых** пакетов сверх установленного профиля (`[web]` ~1,5 ГБ, `[pptx]` ~18 МБ, `[win-office]` ~19,5 МБ и др.) агент **обязан явно запросить подтверждение пользователя**, указав: (1) точный список пакетов, (2) зачем они нужны и (3) ориентировочный объём загрузки.
- **Кодировка (Windows):** в начале каждого Python-скрипта принудительно ставить UTF-8 на `stdout`/`stderr` (`sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')`), чтобы не падать на `cp1251`.
- **Изоляция артефактов (Принцип 8):** все рабочие файлы, выгрузки, черновики и процедурные скрипты сессии хранить **строго внутри `workspace/<тема>/`** (скрипты — в `workspace/<тема>/скрипты/`). Корень проекта, `pipeline/` и `sandbox/` не засорять.
- **Нулевая толерантность к галлюцинациям (Zero Trust):** категорически запрещено выдумывать ссылки, DOI, авторов, численные данные или синтетические URL (No Synthetic Slugs). Работа строго по верифицированному сырью (`results.md`).
- **Право вето человека:** ни один агент не снимает пункты чек-листа и не упрощает требования самостоятельно — только по явному согласию пользователя.
- **Синхронизация с GitHub:** после завершённого смыслового изменения в проекте (или по запросу) запускать `& "C:\Program Files\Git\bin\bash.exe" sync.sh "<описание>"` (на Windows именно Git Bash, не WSL `bash`).

---

## 2. Единая точка входа: адаптивный сценарий сессии

Не нужно жонглировать 5 ролями или просить у пользователя заполнять шаблоны с плейсхолдерами. Ведущий агент сам подбирает глубину сценария под задачу и кратко озвучивает план:

| Трек | Когда применять | Рабочий маршрут |
|---|---|---|
| **S (Точечный)** | 1–3 локальные правки, мелкое форматирование, быстрый lookup без новой библиографии | Правка напрямую + обязательный программный post-check (без лишних файлов и гейтов) |
| **M (Стандартный, дефолт ~80% задач)** | Редактура `.docx`, сборка `.pptx`, работа со статьёй / источниками | `workspace/<тема>/` → **1. Разведка и план** → **2. Фактбаза (`results.md`)** → **3. Текст и сборка** → **4. Программная проверка (+ гейты по чек-листам)** |
| **L (Публикация / Высокий риск)** | Статья в рецензируемый журнал, >10 источников, жёсткий ГОСТ / `References` | Полный цикл: Pre- и Post-factcheck (`results.md`), выделенный Текстовик (внешний **GemBot** / `GemBot → Claude` или opt-in саб-агент `textwriter-agent`) для `[TEXT-N]`, программный аудит + рекомендация независимых саб-агентов-гейтов |

### Паттерн Текстовика (`GemBot Handoff` / саб-агент `textwriter-agent`)
Для объёмной генерации блоков `[TEXT-N]` на основе `results.md` доступны два изолированных режима (оба опциональны; при малом объёме ведущий агент пишет сам):
- **Внешний Текстовик ([Writing Editor / GemBot](https://gemini.google.com/gem/writing-editor) или связка `GemBot → Claude`):** канон — [`pipeline/prompts/textwriter.md`](pipeline/prompts/textwriter.md). Ведущий агент собирает готовый к копипасте `workspace/<тема>/gembot_prompt.md` (вшивая `results.md`, режим `References` и ТЗ вместо `{{...}}`) — оптимально для экономии коммерческих токенов и сред без саб-агентов.
- **Саб-агент `textwriter-agent` (строго по указанию пользователя):** канон — [`pipeline/prompts/subagents/textwriter-agent.md`](pipeline/prompts/subagents/textwriter-agent.md). Работает в чистом контексте (**Read-Only + Zero-Search**, без правки `.docx` и веб-поиска) напрямую по `results.md` и [`editorial-standards.md`](pipeline/docs/editorial-standards.md), без ручного копипаста.
- В обоих режимах полученные `[TEXT-N]` **обязательно** проходят Post-Factcheck (`factcheck-gate` в отдельном контексте/проходе) перед дословной вшивкой в `.docx`/`.pptx`.

---

## 3. Саб-агенты: гейты проверки и opt-in Текстовик (только по согласию + Fallback)

Чтобы убрать слепоту самопроверки (*self-confirmation bias*) и изолировать генерацию от шума разведки, проект использует модульные read-only профили со строгой фиксацией на артефакте (**Scope Pinning**):

| Профиль | Роль | Шаблон брифа | Назначение (Read-Only) |
|---|---|---|---|
| `factcheck-gate` | Гейт | [`pipeline/prompts/subagents/factcheck-gate.md`](pipeline/prompts/subagents/factcheck-gate.md) | Сверка `[TEXT-N]` / фактов / DOI / URL / якорей против `results.md` |
| `audit-gate` | Гейт | [`pipeline/prompts/subagents/audit-gate.md`](pipeline/prompts/subagents/audit-gate.md) | Программная (`python-docx` / `docx diff` / 1080p PNG) + редакционная вычитка артефакта |
| `code-gate` | Гейт | [`pipeline/prompts/subagents/code-gate.md`](pipeline/prompts/subagents/code-gate.md) | Опциональный аудит сложного скрипта правок (`R1–R4`, таблицы, дубли, Windows UTF-8) |
| `textwriter-agent` | Генератор | [`pipeline/prompts/subagents/textwriter-agent.md`](pipeline/prompts/subagents/textwriter-agent.md) | Чистая генерация `[TEXT-N]` по `results.md` + `editorial-standards.md` (Zero-Search; **не гейт**, вывод проверяет `factcheck-gate`) |

> **Правило деликатной активации (Opt-in & Environment-Safe):**
> 1. **Без явного указания пользователя саб-агентов НЕ спавнить** (ни гейты, ни `textwriter-agent`).
> 2. В начале задачи Трека **M / L** (если есть библиография, большой объём текста, важный `.docx`/`.pptx` или нетривиальный скрипт) добавь одну спокойную строку: *«Проект рекомендует подключить саб-агентов (`factcheck-gate` / `audit-gate`, при желании — `textwriter-agent` для `[TEXT-N]`) — сообщите, если среда поддерживает саб-агентов и хотите их активировать»*.
> 3. **Fallback для сред без саб-агентов (напр. OpenSRE) или при отказе:** гейты выполняются ведущим агентом напрямую как отдельный изолированный проход по тем же чек-листам, а роль Текстовика берёт внешний `GemBot` (`gembot_prompt.md`) или ведущий агент.

---

## 4. Маршрутизация контекста (SSOT — что читать под задачу)

Не читай все файлы подряд — открывай только профильный канон под текущую задачу:

| Задача / Модуль | Канонический документ (SSOT) | Инструмент / Скрипт / Навык |
|---|---|---|
| **Архитектура ядра и 8 принципов** | [`pipeline/docs/architecture.md`](pipeline/docs/architecture.md) | Треки `S/M/L`, 4 фазы, GemBot Handoff, саб-агенты-гейты |
| **Стандарты текста и References** | [`pipeline/docs/editorial-standards.md`](pipeline/docs/editorial-standards.md) | Аннотации, 2 режима References (без гибридов), антипаттерны |
| **Схема и уровни фактчекинга** | [`pipeline/docs/cascade.md`](pipeline/docs/cascade.md) | `sam` / `pipeline/sam.py`, вердикты в `pipeline/verdicts.py` |
| **Команды и техконстанты каскада** | [`pipeline/docs/knowledge.md`](pipeline/docs/knowledge.md) | `factcheck_openalex.py` (0.5), `crawl4ai` (2), `scrapling` (3), `firecrawl` (4) |
| **Лёгкий профиль и ручной трек** | [`pipeline/manual/manual.md`](pipeline/manual/manual.md) | `requirements-lite.txt` (`lite`, ~16,5 МБ) + `fetch_lite.py` + `factcheck_manual.py` |
| **Биомедицинский фактчекинг** | [`pipeline/docs/biomed-protocol.md`](pipeline/docs/biomed-protocol.md) | `pipeline/biomed/factcheck_biomed.py` (Ур. 0.7) + 10 навыков в `.agents/skills/` |
| **Правка и вычитка `.docx`** | [`pipeline/docs/docx-protocol.md`](pipeline/docs/docx-protocol.md) | `python-docx`, [`docx_orchestrator.py`](pipeline/templates/docx_orchestrator.py), `hush-docx`, `docx-cli`, `docx-master` |
| **Сборка презентаций `.pptx`** | [`pipeline/docs/presentation-protocol.md`](pipeline/docs/presentation-protocol.md) | `python-pptx`, триада доклада, `fit_in_box`, экспорт 1080p |
| **Исследовательские навыки** | [`pipeline/docs/research-skills.md`](pipeline/docs/research-skills.md) | `deep-research`, `litreview`, `deepread`, `research`, `research-summarizer` |
| **Текстовик (`GemBot` / саб-агент)** | [`pipeline/prompts/textwriter.md`](pipeline/prompts/textwriter.md) / [`textwriter-agent.md`](pipeline/prompts/subagents/textwriter-agent.md) | Внешний `GemBot` (`→ Claude`) или opt-in `textwriter-agent`; `[TEXT-N]` |
| **Журнал крупной сессии (опц.)** | [`pipeline/templates/progress.template.md`](pipeline/templates/progress.template.md) | Опциональный трекер фаз и гейтов для Треков M/L |
| **Написание промптов (PE)** | [`pipeline/docs/llm.md`](pipeline/docs/llm.md) | Руководство по prompt engineering |
