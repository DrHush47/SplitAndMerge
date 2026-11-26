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
| **L (Публикация / Высокий риск)** | Статья в рецензируемый журнал, >10 источников, жёсткий ГОСТ / `References` | Полный цикл: Pre- и Post-factcheck (`results.md`), внешний **GemBot** (или `GemBot → Claude`) для текстов `[TEXT-N]`, программный аудит + рекомендация независимых саб-агентов-гейтов |

### Паттерн GemBot Handoff (внешний Текстовик)
В роли Текстовика часто используется внешний **[Writing Editor (GemBot)](https://gemini.google.com/gem/writing-editor)** (или связка `GemBot → Claude`).
- Шаблон [`pipeline/prompts/textwriter.md`](pipeline/prompts/textwriter.md) остаётся рабочим каноном для GemBot.
- При большом объёме текста или по запросу пользователя ведущий агент **сам собирает** готовый к копипасте файл `workspace/<тема>/gembot_prompt.md` (вшивая `results.md`, выбранный режим `References` и ТЗ вместо `{{...}}`).
- После получения `[TEXT-N]` от пользователя агент обязательно сверяет их с `results.md` и [`pipeline/docs/editorial-standards.md`](pipeline/docs/editorial-standards.md), затем вшивает в `.docx`/`.pptx` дословно.

---

## 3. Саб-агенты-гейты (строго по согласию пользователя + Fallback)

Чтобы убрать слепоту самопроверки (*self-confirmation bias*), проект использует 3 модульных read-only гейта со строгой фиксацией на конкретном артефакте (**Scope Pinning**):

| Гейт | Шаблон брифа | Что проверяет (Read-Only) |
|---|---|---|
| `factcheck-gate` | [`pipeline/prompts/subagents/factcheck-gate.md`](pipeline/prompts/subagents/factcheck-gate.md) | Сверка `[TEXT-N]` / фактов / DOI / URL / якорей против `results.md` |
| `audit-gate` | [`pipeline/prompts/subagents/audit-gate.md`](pipeline/prompts/subagents/audit-gate.md) | Программная (`python-docx` / `docx diff` / 1080p PNG) + редакционная вычитка итогового артефакта |
| `code-gate` | [`pipeline/prompts/subagents/code-gate.md`](pipeline/prompts/subagents/code-gate.md) | Опциональный аудит сложного скрипта правок (`R1–R4`, таблицы, дубли, Windows UTF-8) |

> **Правило деликатной активации (Opt-in & Environment-Safe):**
> 1. **Без явного указания пользователя саб-агентов НЕ спавнить.**
> 2. В начале задачи Трека **M / L** (если есть библиография, важный `.docx`/`.pptx` или нетривиальный скрипт) просто добавь одну спокойную строку: *«Проект рекомендует использовать саб-агент-гейт (`factcheck-gate` / `audit-gate`) в этой задаче — сообщите, если ваша среда поддерживает саб-агентов и хотите их подключить»*.
> 3. **Fallback для сред без саб-агентов (напр. OpenSRE) или при отказе:** ведущий агент выполняет те же чек-листы напрямую как отдельный изолированный проход проверки, не падая и не теряя требований качества.

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
| **Внешний Текстовик (GemBot)** | [`pipeline/prompts/textwriter.md`](pipeline/prompts/textwriter.md) | `GemBot` (Writing Editor) → опционально `Claude`; `[TEXT-N]` |
| **Журнал крупной сессии (опц.)** | [`pipeline/templates/progress.template.md`](pipeline/templates/progress.template.md) | Опциональный трекер фаз и гейтов для Треков M/L |
| **Написание промптов (PE)** | [`pipeline/docs/llm.md`](pipeline/docs/llm.md) | Руководство по prompt engineering |
