# FireCrawl — Ур.4 каскада факт-чекинга (РЕЗЕРВ)

> **Standalone-референс для агента.** В новой сессии без контекста — читай этот документ.
> **Инструмент:** `firecrawl` CLI (платный, резерв — только если Scrapling не справился).
> **Вендор:** [firecrawl.dev](https://firecrawl.dev)
> **Проектные настройки:** вывод — в `workspace/` (вне git). См. `../docs/knowledge.md` §0.1.

## Роль в каскаде

> **Место в каскаде:** Ур.4 — FireCrawl (платный резерв). Полная схема эскалации: [`../docs/cascade.md`](../docs/cascade.md)

**Когда применять:** платный резерв, когда бесплатные уровни не справились; нужен гарантированный markdown-вывод.

**Когда НЕ применять:** простые URL и Cloudflare — сначала бесплатные уровни.

> Порядок эскалации — только в [`../docs/cascade.md`](../docs/cascade.md). Всегда пробовать Scrapling перед FireCrawl.

---

## Quick start

```bash
# Установка (единоразово)
npx -y firecrawl-cli@latest init --all --browser

# Проверка
firecrawl --status
firecrawl credit-usage

# Скрапинг URL в проектную директорию
firecrawl scrape 'https://...' -o workspace/firecrawl_<name>.md
```

---

## Технические константы

> Выходные файлы и очистка `workspace/` — только в [`../docs/knowledge.md`](../docs/knowledge.md) §0.1, здесь не дублируются. Специфика уровня: CLI `firecrawl`; платные кредиты (`firecrawl credit-usage`); встроенная конвертация в markdown.

---

## API — основные команды

| Команда | Назначение | Пример |
|---------|-----------|--------|
| `scrape` | Одна страница → markdown | `firecrawl scrape 'URL' -o out.md` |
| `crawl` | Массовый обход сайта | `firecrawl crawl 'URL' --max-pages 50` |
| `search` | Поиск в интернете | `firecrawl search 'query'` |
| `map` | Карта URL сайта | `firecrawl map 'https://site.com'` |
| `credit-usage` | Остаток кредитов | `firecrawl credit-usage` |

---

## Credit Usage — ОБЯЗАТЕЛЬНО

После **каждого** использования FireCrawl:

```bash
firecrawl credit-usage
firecrawl credit-usage --json --pretty -o workspace/firecrawl_credits.json
```

Цифры записать в `results.md` (секция «Кредиты FireCrawl»). НЕ придумывать — только из вывода команды.

---

## Известные ограничения

1. **Платный.** Использовать только если Scrapling (Ур.3) не справился.
2. **Keyless Free Tier** — есть, но rate-limited. MCP: `https://mcp.firecrawl.dev/v2/mcp`, CLI: `npx -y firecrawl-cli@latest` без логина, API: REST без `Authorization`. Бесплатный аккаунт: https://www.firecrawl.dev/signin
3. **Не для batch-проверок.** Для 10+ URL сначала пробовать Scrapling (бесплатно, batch-режим).

---

## Связанные документы

- `../docs/knowledge.md` — главный cheatsheet каскада фактчекинга
- `../docs/architecture.md` — архитектура конвейера редактуры
- `../scrapling/scrapling.md` — референс Scrapling (Ур.3, основная замена FireCrawl)
- `../openalex/openalex.md` — референс OpenAlex (Ур.0.5)
