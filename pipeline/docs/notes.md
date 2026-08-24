# notes.md — Находки и идеи для интеграции

> **Дата:** 2026-07-16
> **Контекст:** аудит возможностей FreeBuff/Codebuff, поиск бесплатных инструментов для расширения агента.
> **Принцип:** только FREE / open-source / бесплатный тир. Никаких платных подписок.

---

## 1. MCP-серверы (Model Context Protocol)

MCP — стандартный протокол для подключения внешних инструментов к AI-агентам.
Codebuff/FreeBuff поддерживает MCP нативно через `.agents/mcp.json` в корне проекта.

## 1.1 MCP-конфиг проекта

Все MCP-серверы централизованно описаны в **`.agents/mcp.json`** в корне проекта.
Файл использует стандартный формат `mcpServers` (Claude Desktop / Codebuff / FreeBuff).

```bash
# Быстрое подключение нового MCP-сервера:
# 1. Добавь блок в `.agents/mcp.json`
# 2. (опционально) Добавь ключ в .env
# 3. Перезапусти сессию FreeBuff / Codebuff
```

**Текущий состав (`.agents/mcp.json`):**

| Сервер | Команда | Требует ключа | Роль |
|---|---|---|---|
| **Context7** | `npx -y @upstash/context7-mcp` | 🟡 Опционально | Живая документация библиотек |
| **E2B** | `npx -y @e2b/mcp-server` | 🔴 Да (`E2B_API_KEY`) | Песочница для кода |
| **Playwright** | `npx -y @playwright/mcp@latest` | 🟢 Нет | Интерактивный браузер (логин, формы, скриншоты, accessibility tree). Ур.2.5 каскада фактчекинга. Общий Chromium со Scrapling (0 доп. места). |
| **Browser-Use** | `uvx --from browser-use[cli] browser-use --mcp` | 🟡 LLM-ключ | Автономный браузерный агент: LLM сама решает клики/формы/навигацию (agentic). Дополняет Playwright (тот — ручной/DOM, этот — агентный/задачи). |
| **Exa** | `npx -y exa-mcp-server` | 🔴 Да (`EXA_API_KEY`) | Семантический поиск |
| **Fetch** | `uvx mcp-server-fetch` | 🟢 Нет | Получение веб-контента |
| **Filesystem** | `npx -y @modelcontextprotocol/server-filesystem .` | 🟢 Нет | Файловые операции |

> **Brave Search** — удалён из конфига 2026-07-16. Решение: приватный поиск не нужен для текущих задач фактчекинга; researcher-web + Exa покрывают потребности в поиске.

**Ключи:** API-ключи хранятся прямо в `.agents/mcp.json` (в `.gitignore`). Для E2B и Exa — зарегистрируйся и получи ключи (бесплатный тир).

**Файлы конфигурации:**
- `.agents/mcp.json` — единственный MCP-конфиг (single source of truth, дубликат удалён)

**Как добавить новый MCP-сервер:**
1. Добавь блок в `.agents/mcp.json`
2. (опционально) Добавь ключ в `env` блок сервера
3. Перезапусти сессию

**Совместимость:**
- **Codebuff** — поддерживает MCP нативно через `.agents/mcp.json` ✅
- **FreeBuff** — совместимость **экспериментальная** (не подтверждена). Конфиг создан с расчётом на Codebuff; в FreeBuff может потребоваться MCP-прокси.
- **Claude Desktop / Cursor / Windsurf** — формат совместим со стандартом `mcpServers` ✅

**Примечание о `_note` полях в JSON:** поля `_note` в `mcpServers` — служебные комментарии для разработчика. MCP-клиенты их игнорируют. При добавлении нового сервера копируй только стандартные поля (`command`, `args`, `env`).

**Как проверить установку сервера:**
```bash
# Context7 — проверка загрузки (help)
npx -y @upstash/context7-mcp --help

# Context7 — интеграционный тест (Linux/Mac/Git Bash)
# Запуск MCP-сервера на 3 сек → exit code 124 (killed by timeout) = ОК
timeout 3 npx -y @upstash/context7-mcp --transport stdio 2>&1 || true
# Windows (PowerShell): замени timeout на Start-Sleep -Seconds 3; Stop-Process

# Browser-Use — проверка установки (uvx требуется!)
uvx --from "browser-use[cli]" browser-use --help

# Browser-Use — smoke test (Linux/Mac/Git Bash, замени Ctrl+C через 3 сек)
timeout 3 uvx --from "browser-use[cli]" browser-use --mcp 2>&1 || true

# Валидация JSON конфига
python -c "import json; json.load(open('.agents/mcp.json')); print('Valid')"
```

---

### 🥇 Tier 1 — Максимальный импакт

| Сервер | Команда запуска | Что даёт | Статус |
|--------|----------------|----------|--------|
| **Context7** | `npx -y @upstash/context7-mcp` | Живая документация библиотек (без галлюцинаций API). 1000+ пакетов. Без API-ключа. | ✅ Бесплатно |
| **E2B** | `npx -y @e2b/mcp-server` | Изолированная облачная microVM для запуска кода. Python/JS. Безопасно. | ✅ Бесплатный тир |
| **Playwright** | `npx -y @playwright/mcp@latest` | Полноценный браузер: accessibility tree, скриншоты, network interception. | ✅ Open source |

### 🥈 Tier 2 — Серьёзные улучшения

| Сервер | Команда запуска | Что даёт | Статус |
|--------|----------------|----------|--------|
| **Exa** | `npx -y exa-mcp-server` | AI-нативный семантический поиск (понимает смысл, не ключевые слова). Структурированный JSON. | ✅ Бесплатный тир |
| ~~**Brave Search**~~ | ~~`npx -y @anthropic/mcp-server-brave-search`~~ | ❌ Удалён 2026-07-16 — researcher-web + Exa покрывают поиск | Было ~$5/мес |
| **Fetch** | `uvx mcp-server-fetch` | Получение веб-контента в LLM-оптимизированном формате. | ✅ Бесплатно |
| **Filesystem** | `npx -y @modelcontextprotocol/server-filesystem .` | Расширенные файловые операции: поиск, диффы, права. | ✅ Бесплатно |

### 🥉 Tier 3 — Нишевые

| Сервер | Что даёт | Статус |
|--------|----------|--------|
| **Postgres MCP** | SQL-запросы на естественном языке | ✅ Open source |
| **Composio** | 250+ SaaS (GitHub, Slack, Jira, Notion) через один эндпоинт | ✅ Бесплатный тир |
| **Taskade** | Проектный менеджмент: таски, календарь, интеграции | ✅ Бесплатный тир |
| **Tendem** | Сеть из 10,000+ экспертов-людей для верификации фактов | 🟡 Бесплатный тир |

### Где искать ещё

- [Glama.ai/mcp/servers](https://glama.ai/mcp/servers) — крупнейший каталог MCP-серверов
- [Smithery.ai](https://smithery.ai/) — реестр MCP с установкой в один клик
- [terminaltrove.com](https://terminaltrove.com) — совместимость CLI-инструментов

---

## 2. Бесплатные инструменты для фактчекинга / парсинга

Находки из веб-поиска (не интегрированы, кандидаты):

### Парсеры / скраперы

| Инструмент | Что делает | Почему интересен | Статус |
|-----------|------------|------------------|--------|
| **SeleniumBase UC Mode** | Обход Cloudflare + CAPTCHA | Мощнее Scrapling для сверх-защищённых сайтов | ✅ Open source |
| **html-to-markdown** (Golang) | Чистый HTML → Markdown, CLI | Быстрее Python-аналогов, конфигурируемые правила | ✅ Open source |
| **Microsoft MarkItDown** | PDF, DOCX, HTML, XLSX, PPTX → Markdown | Универсальный конвертер. **Отменён** для нашего проекта. | ✅ Open source |
| **MinerU / PDF-Extract-Kit** | Высокоточное извлечение из научных PDF: текст, таблицы, формулы → Markdown/JSON | Специально обучен на научных статьях. Закрывает пробел обработки PDF. | ✅ Open source |
| **Unstract** | No-code ETL для документов, self-hosted | Автоматическая структуризация документов для LLM | ✅ Open source |

### Академическая верификация

| Инструмент | Что делает | Почему интересен | Статус |
|-----------|------------|------------------|--------|
| **OpenAlex API** | Бесплатная (CC0) замена Scopus/WoS. REST API для DOI lookup. | ✅ **Уже интегрирован** как Ур.0.5 каскада | ✅ Бесплатно |
| **RefChecker** | Валидация ссылок против Semantic Scholar, OpenAlex, CrossRef, DBLP. Ловит галлюцинации. | Python-пакет. Кандидат на Ур.0.6 или Ур.1.5. | ✅ Open source |
| **paperscraper** | Массовый сбор метаданных из PubMed, arXiv, bioRxiv, medRxiv | Для систематических обзоров | ✅ Open source |
| **OpenFactCheck** | Оценка фактологичности LLM-выводов (claim decomposition + evidence retrieval) | Валидация выходов Текстовика | ✅ Open source |

### Поисковые API

| Инструмент | Что делает | Бесплатный тир | Статус |
|-----------|------------|----------------|--------|
| **Tavily** | Поиск, оптимизированный под AI-агентов (чистый текст + relevance scoring) | 1000 запросов/мес | Кандидат |
| **Exa** | Семантический/нейронный поиск (понимает intent) | Да | Кандидат |
| **Serper** | SERP-скрапинг Google | 2500 запросов | Кандидат |
| **Perplexity Sonar** | Синтез с цитатами | 100 запросов/день | Second opinion |

---

## 3. npx skills — магазин навыков

Codebuff поддерживает установку community-навыков через `npx skills`:

```bash
# Поиск навыка
npx skills find <query>

# Просмотр навыков в репозитории
npx skills add <owner/repo> --list

# Установка конкретного навыка
npx skills add <owner/repo> --skill <name> --yes
```

Навыки устанавливаются в `.agents/skills/` и загружаются через `skill` tool.

### Идеи для поиска навыков

- `npx skills find "pdf parser"` — извлечение текста из PDF
- `npx skills find "diagram generator"` — генерация Mermaid/PlantUML диаграмм
- `npx skills find "git workflow"` — автоматизация git
- `npx skills find "api tester"` — тестирование REST API
- `npx skills find "code review checklist"` — чек-листы для код-ревью

---

## 4. Что уже есть у FreeBuff «из коробки»

> ⚠️ **Важно:** перечисленные ниже инструменты — это суб-агенты **рантайм-среды FreeBuff/Codebuff**, а не часть кодовой базы `pipeline/`. Они доступны агенту во время исполнения, но не хранятся в репозитории.

| Возможность | Инструмент | Сила |
|---|---|---|
| Терминал | `basher` — любой shell, Python, npm | 💪 |
| Файлы | `read_files`, `write_file`, `str_replace`, `glob` | 💪 |
| Веб-поиск | `researcher-web`, `researcher-docs` | 🟡 |
| Браузер | MCP: `browser-use` (агентный) или `playwright` (DOM/DOM-дерево) — см. секцию 1 | 🟡 |
| Скрапинг | `FireCrawl` (навыки + CLI) | 💪 (платные кредиты) |
| Код-ревью | `code-reviewer-deepseek` | 💪 |
| Мышление | `thinker-with-files-gemini`, `thinker-gpt` | 💪 |
| Поиск по коду | `code-searcher` (ripgrep) | 💪 |
| SaaS-подбор | `gravity_index` | 🟡 |
| Навыки | `skill` (загрузка .md-инструкций) | 💪 |
| MCP | Платформа Codebuff поддерживает | 🟢 |
| Интерактивный CLI | `tmux-cli` | 🟡 |

---

## 5. План идеального FreeBuff (видение)

Если активировать ВСЕ находки, агент выглядит так:

```
FreeBuff MAX:
│
├── 🧠 thinker-gemini / thinker-gpt       (глубокий анализ)
├── 🔍 researcher-web                     (базовый поиск)
├── 🔍 Exa MCP                            (AI-поиск, активен)
├── ~~🔍 Brave Search MCP~~                (удалён 2026-07-16)
├── 📖 Context7 MCP                       (живая документация)
├── 🌐 browser-use / Playwright MCP       (браузер)
├── 🖥️  basher                             (терминал)
├── 🏖️  E2B MCP                            (песочница для кода)
├── 🔥 FireCrawl                          (скрапинг)
├── 📁 read_files / write_file / Filesystem MCP
├── 📦 npx skills                         (магазин навыков)
├── 🔌 .agents/mcp.json                   (MCP-хаб)
├── 🗄️  Postgres MCP                       (базы данных)
├── 🔗 Composio MCP                       (250+ SaaS-интеграций)
└── ✅ OpenAlex API                       (проверка DOI, уже интегрирован)
```

---

## 6. Что уже сделано (проект pipeline)

> Проект находится в папке `pipeline/`. Каскад фактчекинга — в [`knowledge.md`](knowledge.md). Протокол .docx — в [`docx-protocol.md`](docx-protocol.md).

### Интегрированные инструменты

| Инструмент | Папка | Скрипт | Документация |
|-----------|-------|--------|-------------|
| **OpenAlex API** | `openalex/` | `factcheck_openalex.py` | `openalex/openalex.md` |
| **Crawl4AI** | `crawl4ai/` | `factcheck_crawl4ai.py` | `docs/knowledge.md` |
| **Scrapling** | `scrapling/` | `factcheck_scrapling.py` | `scrapling/scrapling.md` |
| **FireCrawl** | `firecrawl/` | CLI-команды | `firecrawl/firecrawl.md` |

### Документация

- `docs/knowledge.md` — каскад фактчекинга (8 уровней, техконстанты)
- `docs/docx-protocol.md` — протокол правки .docx (правила, шаблоны, антипаттерны)
- `docs/architecture.md` — архитектура конвейера (роли, этапы, принципы)

---

## 7. Приоритеты внедрения (рекомендация)

### ✅ Уже сделано

- **Context7 MCP** — живая документация (в `.agents/mcp.json`)
- **E2B MCP** — песочница для кода (в `.agents/mcp.json`)
- **Playwright MCP** — интерактивный браузер: логин, формы, скриншоты, низкоуровневый DOM (в `.agents/mcp.json`)
- **Browser-Use MCP** — автономный браузерный агент: LLM сама планирует клики/формы/навигацию (в `.agents/mcp.json`, нужен LLM-ключ)
- **Exa MCP** — семантический поиск (в `.agents/mcp.json`)
- **Fetch MCP** — веб-контент (в `.agents/mcp.json`)
- **Filesystem MCP** — файловые операции (в `.agents/mcp.json`)

### 🔴 Сейчас

1. **Подключить RefChecker** — детектор галлюцинированных ссылок
2. **Вставить реальные ключи** E2B, Exa и Browser-Use (OpenAI **или** Anthropic — достаточно одного) в `.agents/mcp.json` (сейчас placeholders)

### ✅ Smoke-тесты (2026-07-18)

- **`uv` / `uvx`** — установлен через `winget` (v0.11.29, astral-sh.uv). Для Git Bash после установки winget нужно вручную добавить в PATH или перезапустить терминал.
- **Browser-Use `--help`** — ✅ загрузились 102 пакета, CLI работает.
- **Browser-Use `--mcp` smoke** — ✅ MCP-сервер стартует без ошибок (timeout 5 сек).
- **Browser-Use `--doctor`** — Chrome ✅, daemon ❌ (не нужен для MCP-режима), cloud auth ❌ (опционально).

> **Путь uv в winget:** `%LOCALAPPDATA%\Microsoft\WinGet\Packages\astral-sh.uv_*\`
> **Git Bash fix:** `export PATH="$PATH:$LOCALAPPDATA/Microsoft/WinGet/Packages/astral-sh.uv_*/"` в `~/.bashrc`.

### 🟡 В следующем цикле

3. **npx skills find** — разведка community-навыков
4. **MinerU** — обработка научных PDF
5. **Tavily API** — AI-оптимизированный поиск
6. **Composio MCP** — SaaS-интеграции
7. **OpenFactCheck** — валидация LLM-выводов

---

## 8. Полезные ссылки

- [modelcontextprotocol.io](https://modelcontextprotocol.io) — официальная документация MCP
- [glama.ai/mcp/servers](https://glama.ai/mcp/servers) — каталог MCP-серверов
- [smithery.ai](https://smithery.ai/) — реестр MCP
- [openalex.org](https://openalex.org) — открытый индекс научных работ (CC0)
- [github.com/markrussinovich/refchecker](https://github.com/markrussinovich/refchecker) — валидатор ссылок
- [github.com/opendatalab/MinerU](https://github.com/opendatalab/MinerU) — извлечение из PDF
- [github.com/D4Vinci/Scrapling](https://github.com/D4Vinci/Scrapling) — stealth-парсер
- [firecrawl.dev](https://firecrawl.dev) — платный скрапинг (резерв)
- [tavily.com](https://tavily.com) — AI-поиск
- [exa.ai](https://exa.ai) — семантический поиск
- [e2b.dev](https://e2b.dev) — песочница для кода
- [context7.com](https://context7.com) — живая документация
- [skills.sh](https://skills.sh/) — каталог npx skills
- [github.com/addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) — золотой стандарт SDLC-воркфлоу
- [github.com/vercel-labs/skills](https://github.com/vercel-labs/skills) — CLI-экосистема навыков

---

## 9. Новые MCP-серверы (июль 2026)

### 🎬 Kinocut — AI видеомонтаж

- **GitHub:** [KyaniteLabs/kinocut](https://github.com/KyaniteLabs/kinocut)
- **Лицензия:** Apache-2.0 | **Цена:** Бесплатно
- AI планирует, режет, склеивает видео по текстовому описанию
- Каждое действие — криптографический «чек» (JSON receipt) для аудита
- Preflight-валидация: отклоняет невыполнимые команды ДО рендера
- Заточен под переработку длинных видео → Shorts/Reels с авто-субтитрами
- **Интеграция:** MCP-сервер, `npx`

### 🏠 Home Assistant MCP — умный дом

- **GitHub:** [homeassistant-ai/ha-mcp](https://github.com/homeassistant-ai/ha-mcp)
- **Цена:** Бесплатно (локально)
- Не просто вкл/выкл устройства — AI создаёт и отлаживает автоматизации
- Читает системные логи для диагностики («почему датчик не сработал?»)
- Умный поиск инструментов (BM25) — не забивает контекст лишним
- Режим read-only для безопасности
- **Интеграция:** MCP-сервер, требует Home Assistant

### 🎵 MusicAgentKit — AI-диджей

- **GitHub:** [sebsto/MusicAgentKit](https://github.com/sebsto/MusicAgentKit)
- **Цена:** Бесплатно
- «Найди трек со вчерашней тренировки и добавь в Chill-плейлист»
- Управление локальной фонотекой: поиск, очереди, плейлисты, метаданные
- Контекстное понимание музыкальной библиотеки
- **Интеграция:** MCP-сервер

### Тренды MCP (июль 2026)

| Тренд | Описание |
|-------|----------|
| **Fail-Closed Design** | Серверы отклоняют неоднозначные команды вместо додумывания |
| **Provenance** | Встроенные audit-логи (JSON receipts) для проверяемости AI-действий |
| **Context Optimization** | Умный поиск инструментов вместо загрузки всех в контекст |
| **Human-in-the-loop** | Read-only режимы и чекпойнты для необратимых операций |

---

## 10. Agent Skills — экосистема навыков

### Что такое Agent Skills

Не просто инструкции, а **воркфлоу с чекпойнтами**. Markdown-файлы, которые заставляют AI следовать senior-уровневым инженерным практикам.

- **Anti-rationalization таблицы** — список отмазок AI («тест не нужен, слишком просто») + rebuttal
- **Чекпойнты** — write failing test → run it → watch it fail → write code
- **Портабельность** — работают в Cursor, Claude Code, Codebuff

### Ключевые репозитории

| Репозиторий | Что даёт |
|-------------|----------|
| **[addyosmani/agent-skills](https://github.com/addyosmani/agent-skills)** | Золотой стандарт: spec → plan → build → test → review → ship |
| **[vercel-labs/skills](https://github.com/vercel-labs/skills)** | CLI-экосистема (`npx skills`), менеджер пакетов навыков |
| **[stitch-kit](https://github.com/topics/ai-agent-skills)** | Дизайн-суперсилы: UI-генерация, дизайн-системы, продакшн-конвертация |

### Популярные воркфлоу

| Воркфлоу | Что делает |
|----------|-----------|
| `/spec` | Проверяет дизайн-документы и scope ДО кодинга |
| `/test` | TDD: красный → зелёный, Beyoncé Rule (полюбил — поставь тест) |
| `/review` | Атомарные коммиты, PR <100 строк, trunk-based development |
| `/ship` | Стандартизированный деплой |
| `/code-simplify` | Chesterton's Fence — не удаляй код пока не объяснишь зачем он |

### Установка

```bash
npx skills add addyosmani/agent-skills --skill spec --yes
npx skills add vercel-labs/skills --skill pr-review --yes
```

---

## 11. CLI-инструменты для AI-агентов

Все бесплатные, запускаются через `basher`, выводят JSON где возможно.

### Изображения

| Инструмент | Команда | Установка |
|-----------|---------|----------|
| **ImageMagick** | `magick img.jpg -resize 50% out.png` | `winget install ImageMagick` |
| **Tesseract OCR** | `tesseract img.png out --output-format json` | `winget install tesseract` |

### Аудио

| Инструмент | Команда | Установка |
|-----------|---------|----------|
| **Whisper** (whisper.cpp) | Офлайн-транскрибация, CPU, один бинарник | `pip install openai-whisper` |
| **Piper** (TTS) | Локальный синтез речи | `pip install piper-tts` |

### Видео

| Инструмент | Команда | Установка |
|-----------|---------|----------|
| **FFmpeg** | `ffmpeg -i video.mp4 -vf "select=eq(n\,10)" frame.jpg` | `winget install ffmpeg` |
| **yt-dlp** | `yt-dlp -j "URL"` (JSON-вывод) | `pip install yt-dlp` |

### Данные

| Инструмент | Команда | Установка |
|-----------|---------|----------|
| **jq** | `jq '.items[].name' data.json` | `winget install jqlang.jq` |
| **csvkit** | `csvsql --query "SELECT *" data.csv` | `pip install csvkit` |

### Сеть

| Инструмент | Команда | Установка |
|-----------|---------|----------|
| **curl** | `curl -s https://api.example.com` | Встроен |
| **httpie** | `https api.example.com` (цветной JSON) | `pip install httpie` |

### Система

| Инструмент | Команда | Установка |
|-----------|---------|----------|
| **btop** | Красивый мониторинг ресурсов | `winget install btop` |

### Паттерны использования

1. **JSON Always** — флаг `-j` или `--output-format json` где возможно
2. **Dry-Run** — AI печатает команду перед выполнением
3. **Combine** — `ImageMagick → Tesseract = OCR после предобработки`
4. **Pipe** — `yt-dlp -j URL | jq '.title'`
