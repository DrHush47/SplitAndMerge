# research-skills.md — Исследовательские навыки конвейера

> **Канон по 5 установленным исследовательским навыкам.** Методологическая надстройка
> над каскадом — схему 7 уровней, словарь вердиктов и техконстанты НЕ расширяет
> и не дублирует: схема — только в [`cascade.md`](cascade.md), команды уровней —
> только в [`knowledge.md`](knowledge.md) §0.1.
>
> **Происхождение:** отобраны из входящего буфера (15 кандидатов, буфер удалён
> после установки: `deep-research`, `litreview`, `deepread`, `research`)
> + из раздела `product-team` upstream-репо (`research-summarizer` — закрывает
> сверку контента источников с текстом статьи);
> установлены в `.agents/skills/` — 5 навыков. Остальные кандидаты отклонены
> (в конвейере не используются).
> Локальные навыки — вне `skills-lock.json` (как `hush-*`, см. `README.md`).

## 1. Карта применения (навык → роль → этап)

| Навык | Путь | Роль | Этапы | Задача |
|---|---|---|---|---|
| `deep-research` | `.agents/skills/deep-research/SKILL.md` | Факт-чекер (методология) | 3, 4.5, точечные вызовы | Дисциплинированное расследование дорогого вопроса: falsifiable-гипотезы, параллельный fan-out, триангуляция ≥3 независимых источников разных типов, обязательный adversarial-pass, каждый источник — отдельным файлом с verbatim-цитатой |
| `litreview` | `.agents/skills/litreview/SKILL.md` | Факт-чекер (поиск) | 3, 4.5 | Академический поиск по бесплатной полосе PubMed E-utilities + OpenAlex (без ключа): PICO / SPIDER / Decomposition, era-gating, cross-search intelligence (repeat-hits, recurring authors). Результат — `results.md` как сырьё для Текстовика |
| `deepread` | `.agents/skills/deepread/SKILL.md` | Рецензент | 1, 5 | Доказательное чтение supplied-материала: центральный тезис, argument tree, evidence ledger с метками уверенности (позиция автора / факт источника / вывод / unverified). Режимы `quick/deep/map/feynman/book`, по умолчанию `deep` |
| `research` | `.agents/skills/research/SKILL.md` | Со-оркестратор (маршрутизация) | 2, 6 | Гибридный роутер: детерминированная классификация → делегация специалисту (`litreview`/`deepread`) или собственный fallback `plan-decompose-search-synthesize-cite`. Решение о маршруте всегда озвучивается, молча не делегирует |
| `research-summarizer` | `.agents/skills/research-summarizer/SKILL.md` | Факт-чекер (выжимка) | 3, 4.5 | Структурированная выжимка каждого источника: тезис → находки (каждая с доказательством) → дословные цитаты с якорем (раздел/страница). Правило: факт без якоря на Этапе 4.5 = `UNCERTAIN`. Скрипты: `extract_citations.py` (сверка цитат с библиографией), `format_summary.py` (пустые каркасы выжимок) |

## 1.1 Доступные специалисты (обязательное ограничение роутера)

Установлены `litreview`, `deepread` и `research-summarizer`; остальные специалисты
роутера (`pulse`, `grants`, `syllabus`, `patent`, `dossier`) **отсутствуют**.
`scripts/classifier.py` про установку не знает и может вернуть
`route_to` в отсутствующего специалиста — такой вердикт считать
недоступным маршрутом и идти в собственный fallback
`plan-decompose-search-synthesize-cite` (см. `fallback_decomposer.py`).
Молча делегировать в неустановленный навык запрещено.
`research-summarizer` в реестре роутера нет — вызывается напрямую
Факт-чекером на Этапах 3/4.5, а не через `classifier.py`.

## 2. Что навыки НЕ делают (границы)

1. **Не добавляют уровней каскада.** Работают *внутри* существующих уровней
   (преимущественно Ур.1 `researcher-web` как методология сбора и сверки) —
   эскалация по-прежнему только по [`cascade.md`](cascade.md).
2. **Не заменяют скрипты Ур.0.5/2/3.** `free_search.py` дополняет OpenAlex-поиск
   полосой PubMed, но программная DOI-сверка остаётся за
   `pipeline/openalex/factcheck_openalex.py`.
3. **Не генерируют библиографию для Текстовика.** Текстовик берёт источники
   ТОЛЬКО из `{{МАТЕРИАЛ}}` (`results.md`); навыкам запрещено «искать более
   подходящие» статьи (см. катастрофу промпта v2 в [`architecture.md`](architecture.md)).
4. **Не выносят вердикты.** Вердикты `CONFIRMED / REFUTED / UNCERTAIN / BLOCKED` —
   только по словарю [`cascade.md`](cascade.md); навыки дают evidence,
   вердикт выносит Факт-чекер (+ человек на Ур.5).
5. **Выжимки — не статья.** `research-summarizer` готовит сырьё для `results.md`,
   а не текст статьи; `.docx`-сборку и оформление ссылок (ГОСТ/журнальный стиль,
   не APA/IEEE из `references/citation-formats.md`) ведут конвейерные роли.

## 3. Запуск скриптов (stdlib-only, без установки)

Запускать корневым `.venv` (единообразие с §0.1 [`knowledge.md`](knowledge.md)):

```bash
# litreview: бесплатный поиск (PubMed + OpenAlex), без ключа
.venv/Scripts/python.exe .agents/skills/litreview/scripts/free_search.py --query "LLM clinical reasoning" --source both --max 10
.venv/Scripts/python.exe .agents/skills/litreview/scripts/framework_recommender.py --help
.venv/Scripts/python.exe .agents/skills/litreview/scripts/citation_tracker.py --help
.venv/Scripts/python.exe .agents/skills/litreview/scripts/cross_search_aggregator.py --help

# research: детерминированная маршрутизация
.venv/Scripts/python.exe .agents/skills/research/scripts/classifier.py --question "..." --output json
.venv/Scripts/python.exe .agents/skills/research/scripts/fallback_decomposer.py --question "..."
.venv/Scripts/python.exe .agents/skills/research/scripts/routing_transparency_logger.py --help

# research-summarizer: выжимки и сверка цитат
.venv/Scripts/python.exe .agents/skills/research-summarizer/scripts/format_summary.py --template academic
.venv/Scripts/python.exe .agents/skills/research-summarizer/scripts/extract_citations.py results.md --output json
```

`deep-research` и `deepread` скриптов не имеют — это pure-методологии
(план/триангуляция/adversarial-pass и режимы чтения соответственно);
их `references/` читаются по мере вызова, целиком не копируются в отчёты.

## 4. Зависимости

- Обязательно: исходящий HTTPS (PubMed E-utilities ≤3 запр./сек; OpenAlex polite pool
  через `--mailto` — быстрее и надёжнее).
- Опционально: Consensus MCP — только как усиливающая полоса `litreview`
  (наличие проверяется в рантайме, отсутствие — не ошибка, тиры планов не детектируются).
- НЕ требуется: платные ключи, browser automation, Node.js (`.docx`-генераторы
  навыков не используются — сборка документов идёт через `python-docx`
  по [`docx-protocol.md`](docx-protocol.md)).

## 5. Дисциплина (общее для всех четырёх)

- Цитировать только то, что вернули вызовы **этой** сессии; тренировочные знания
  помечать и из подсчётов исключать; тонкие результаты заявлять явно, не добивать выдумкой.
- Каждый факт в `results.md` — с якорем (раздел/страница/цитата источника
  по формату `research-summarizer`); факт без якоря на Этапе 4.5 = `UNCERTAIN`.
- `extract_citations.py results.md --output json`: `total` обязан сходиться
  с числом библиографии; расхождение — расследовать, не замалчивать.
- Последовательные запросы — 1 запр./сек на платформу; на сбой — ждать 3 сек,
  ретрай один раз; после 3 подряд сбоев — стоп, отдать собранное.
- `research`-маршрутизация — всегда вслух: «роутим в X, потому что …; возрази,
  если нужен другой маршрут»; silent-route только при ≥2 сигналах или одной
  сильной многословной фразе.

## Связанные документы

- [`cascade.md`](cascade.md) — схема 7 уровней, эскалация, словарь вердиктов (единственный источник)
- [`knowledge.md`](knowledge.md) — техконстанты и команды запуска (§0.1)
- [`architecture.md`](architecture.md) — роли и гейты (Роль 5, Этапы 1, 3, 4.5, 5)
- [`docx-protocol.md`](docx-protocol.md) — протокол правки `.docx` (навыки `.docx`-сборку не ведут)
