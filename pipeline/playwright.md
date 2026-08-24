# Playwright MCP — Ур.2.5 каскада факт-чекинга

> **Standalone-референс для агента.** В новой сессии без контекста — читай этот документ.
> **Основной инструмент:** `@playwright/mcp@latest` (MCP-сервер, KEYLESS)
> **Вендор:** [github.com/microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp)
> **Лицензия:** Apache-2.0

## Роль в каскаде

```
Ур.0.5 → OpenAlex API           (мгновенная проверка DOI)
Ур.1   → researcher-web         (поиск фактов)
Ур.2   → Crawl4AI               (базовый HTTP-парсинг)
Ур.2.5 → Playwright MCP         ← ТЫ ЗДЕСЬ (бесплатно, KEYLESS, интерактив)
Ур.3   → Scrapling StealthySession (обход Cloudflare, batch-режим)
Ур.4   → FireCrawl              (платный резерв)
Ур.5   → Человек                (ручная верификация)
Ур.6   → Gemini DeepSearch      (опционально)
```

**Когда применять Playwright MCP:**
- Crawl4AI (Ур.2) вернул EMPTY/CONFIRMED, но контент скрыт за логином/формой
- Сайт требует взаимодействия: пагинация, поиск, фильтры, загрузка файлов
- Нужен скриншот страницы для ручной верификации
- Нужен accessibility tree или network log для отладки блокировок
- JS-heavy SPA без anti-bot защиты

**Когда НЕ применять:**
- Простые статические URL → Crawl4AI (быстрее)
- Сайты с Cloudflare/DataDome → Scrapling (Ур.3, специализирован)
- Batch из 10+ URL → Scrapling (держит браузер открытым, 10-20× быстрее)

---

## Quick start

```bash
# Запуск MCP-сервера (через MCP-клиент Codebuff/FreeBuff)
npx -y @playwright/mcp@latest

# Или через `.agents/mcp.json` (уже настроен в корне проекта)
```

**Не требует API-ключа.** Запускается локально, использует Chromium.

**По умолчанию браузер — headed (видимый).** Для headless: `npx -y @playwright/mcp@latest --headless`.

---

## Общий движок со Scrapling

Playwright MCP и Scrapling (Ур.3) используют **один и тот же Chromium**:
- Путь: `C:\Users\<user>\AppData\Local\ms-playwright\`
- Размер: ~1.6 GB (уже занято Scrapling)
- **Дополнительное место на диске: 0 байт**

---

## API (MCP-инструменты) — проверено по v0.0.78

### Навигация и страницы

| Инструмент | Назначение | Пример |
|-----------|-----------|--------|
| `browser_navigate(url)` | Открыть страницу | `browser_navigate("https://vk.com")` |
| `browser_tabs` | Управление вкладками (открыть/закрыть/переключить) | `browser_tabs` |

### Взаимодействие со страницей

| Инструмент | Назначение | Пример |
|-----------|-----------|--------|
| `browser_click(selector)` | Кликнуть элемент | `browser_click("button.login")` |
| `browser_type(selector, text)` | Ввести текст | `browser_type("#email", "user@mail.ru")` |
| `browser_press_key(key)` | Нажать клавишу | `browser_press_key("Enter")` |
| `browser_wait_for(condition)` | Дождаться состояния (load, selector, timeout) | `browser_wait_for(".loaded")` |

### DOM и JavaScript

| Инструмент | Назначение | Пример |
|-----------|-----------|--------|
| `browser_snapshot()` | Accessibility tree (текст) | `browser_snapshot()` |
| `browser_take_screenshot()` | Скриншот страницы | `browser_take_screenshot()` |
| `browser_evaluate(js)` | Выполнить JS на странице | `browser_evaluate("document.title")` |

### Сеть и состояние

| Инструмент | Назначение | Пример |
|-----------|-----------|--------|
| `browser_network_requests()` | Перехваченные запросы | `browser_network_requests()` |

> **Примечание:** доступные `--caps`: `vision`, `pdf`, `devtools`. Cookie/storage инструменты могут быть доступны в других версиях. Полный список — через `tools/list` в работающем MCP-сервере.

**Всего: 10 подтверждённых инструментов** (исправлено по рецензии 2026-07-16 — удалены 8 выдуманных).

**ВАЖНО:** `page.markdown` — **НЕ СУЩЕСТВУЕТ** (как и у Scrapling). Для markdown-вывода используй Crawl4AI (Ур.2) или FireCrawl (Ур.4).

---

## Технические константы

| Параметр | Значение |
|---|---|
| **Запуск** | `npx -y @playwright/mcp@latest` (MCP-сервер) |
| **Тип** | MCP-сервер, KEYLESS |
| **Браузер** | Chromium (headed по умолчанию), общий со Scrapling |
| **Таймаут** | Определяется MCP-клиентом (~30 сек на операцию) |
| **Стоимость** | Бесплатно (локальный Playwright) |
| **Диск** | 0 байт дополнительно (Chromium уже установлен) |

---

## Стратегия применения

```
Шаг 1: Crawl4AI пробует загрузить страницу
         ↓
Шаг 2: Если EMPTY / контент скрыт за формой/логином
         ↓
Шаг 3: Playwright MCP открывает браузер, логинится/заполняет форму
         ↓
Шаг 4: Если Cloudflare блокирует → Scrapling (Ур.3)
         ↓
Шаг 5: Если ничего не помогло → FireCrawl (Ур.4, платный)
```

---

## Пример: логин и отправка сообщения

```python
# Playwright MCP через MCP-клиент:
# 1. browser_navigate("https://example.com/login")
# 2. browser_type("#username", "user")
# 3. browser_type("#password", "pass")
# 4. browser_click("button[type=submit]")
# 5. browser_take_screenshot()  # подтверждение входа
```

---

## Сравнение с другими уровнями каскада

| Параметр | Playwright MCP (Ур.2.5) | Crawl4AI (Ур.2) | Scrapling (Ур.3) |
|---|---|---|---|
| **Интерактивность** | ✅ Клики, формы | ❌ Только чтение | ❌ Только чтение |
| **Cloudflare bypass** | ❌ | ❌ | ✅ StealthySession |
| **Batch-режим** | ❌ Один URL за раз | ✅ | ✅ 10-20× быстрее |
| **Скриншоты** | ✅ | ❌ | ❌ |
| **Markdown-вывод** | ❌ | ✅ | ❌ |
| **Стоимость** | Бесплатно | Бесплатно | Бесплатно |
| **Скорость (1 URL)** | ~2-5 сек | ~1 сек | ~3-5 сек |

---

## Известные ограничения

1. **Не обходит Cloudflare.** Для anti-bot защиты — Scrapling (Ур.3).
2. **Нет batch-режима.** Каждый URL — отдельная сессия. Для 10+ URL — Scrapling быстрее.
3. **Требует MCP-клиент.** Не запускается как standalone Python-скрипт — только через Codebuff/FreeBuff/Claude Desktop.
4. **Headed по умолчанию.** Визуальный браузер. Для headless: `npx -y @playwright/mcp@latest --headless`.

---

## Связанные документы

- `docs/knowledge.md` — полный протокол работы (каскад, .docx, техконстанты)
- `docs/architecture.md` — архитектура конвейера редактуры
- `scrapling/scrapling.md` — референс Scrapling (Ур.3, общий Chromium)
- `firecrawl/firecrawl.md` — референс FireCrawl (Ур.4 резерв)
- `openalex/openalex.md` — референс OpenAlex (Ур.0.5)
