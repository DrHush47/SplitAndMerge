# FireCrawl — Ур.4 каскада факт-чекинга (РЕЗЕРВ)

> **Standalone-референс для агента.** В новой сессии без контекста — читай этот документ.
> **Инструмент:** `firecrawl` CLI (платный, резерв — только если Scrapling не справился).
> **Вендор:** [firecrawl.dev](https://firecrawl.dev)
> **Проектные настройки:** вывод — в `workspace/` (вне git). См. `../docs/knowledge.md` §0.1.

## Роль в каскаде

> **Место в каскаде:** Ур.4 — FireCrawl (платный резерв). Полная схема эскалации: [`../docs/cascade.md`](../docs/cascade.md)

**Когда применять:**
- Scrapling (Ур.3) вернул EMPTY/ERROR/пустой контент
- Сайт с неизвестной anti-bot защитой, которую не берёт Scrapling
- Требуется гарантированный markdown-вывод (Scrapling не имеет `page.markdown`)

**Когда НЕ применять:**
- Простые статические URL → Crawl4AI (бесплатно, быстрее)
- Сайты с Cloudflare → Scrapling (бесплатно)
- **Всегда пробовать Scrapling перед FireCrawl — экономия кредитов.**

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

| Параметр | Значение |
|---|---|
| **CLI** | `firecrawl` (глобально после `npx init`) |
| **Выходные файлы** | `workspace/firecrawl_<name>.md` |
| **Таймаут** | Определяется CLI (~30-60 сек на URL) |
| **Стоимость** | Платные кредиты (проверять: `firecrawl credit-usage`) |
| **Markdown** | ✅ Встроенная конвертация (в отличие от Scrapling) |

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
