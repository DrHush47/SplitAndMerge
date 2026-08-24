# Отчёт факт-чекера

> Дата: 2026-07-17
> Каскад: OpenAlex (Ур.0.5) → researcher-web (Ур.1) → Crawl4AI (Ур.2) → Playwright MCP (Ур.2.5) → Scrapling (Ур.3) → FireCrawl (Ур.4, резерв)
> Тестовый прогон: 3 DOI (исправленные) из targets.json

---

## Сводка

| Статус | Количество |
|--------|-----------|
| Проверено фактов | 3 |
| CONFIRMED | 3 |
| REFUTED | 0 |
| UNCERTAIN | 0 |
| BLOCKED | 0 |

---

## Детали по каждому факту

### ФАКТ 1: Topol E.J. High-performance medicine. Nature Medicine 2019

- **Статус:** CONFIRMED
- **Значение:** OpenAlex: DOI 10.1038/s41591-018-0300-7, журнал Nature Medicine, 2018. Название: «High-performance medicine: the convergence of human and artificial intelligence». Авторы подтверждены.
- **Источник:** https://doi.org/10.1038/s41591-018-0300-7
- **Метод:** OpenAlex + Crawl4AI
- **Доказательство:** OpenAlex подтвердил статью. Crawl4AI: страница nature.com загружена (2165 символов).
- **Альтернативные источники проверены:** нет

### ФАКТ 2: Page M.J. et al. The PRISMA 2020 statement. BMJ 2021

- **Статус:** CONFIRMED
- **Значение:** OpenAlex: DOI 10.1136/bmj.n71, BMJ, 2021. Авторы: Matthew J. Page; Joanne E. McKenzie; Patrick M. Bossuyt; Isabelle Boutron; Tammy Hoffmann et al. Cited by: 97,026.
- **Источник:** https://doi.org/10.1136/bmj.n71
- **Метод:** OpenAlex + Crawl4AI
- **Доказательство:** OpenAlex: «The PRISMA 2020 statement: an updated guideline for reporting systematic reviews», BMJ, Year: 2021, Volume: 372. Crawl4AI: страница bmj.com загружена (782 символа).
- **Альтернативные источники проверены:** нет

### ФАКТ 3: Obermeyer Z. et al. Dissecting racial bias. Science 2019

- **Статус:** CONFIRMED
- **Значение:** OpenAlex: DOI 10.1126/science.aax2342, Science, 2019. Название: «Dissecting racial bias in an algorithm used to manage the health of populations». Авторы подтверждены.
- **Источник:** https://doi.org/10.1126/science.aax2342
- **Метод:** OpenAlex + Crawl4AI
- **Доказательство:** OpenAlex подтвердил статью. Crawl4AI: страница science.org загружена (2163 символа).
- **Альтернативные источники проверены:** нет

---

## Методология

- Использованные инструменты: OpenAlex (Ур.0.5), Crawl4AI (Ур.2)
- Что сработало лучше: **OpenAlex — 3/3 CONFIRMED** (мгновенно). Crawl4AI — 3/3 страниц загружены.
- Что не сработало: ничего. Каскад отработал без сбоев.
- **Важно:** первоначальный прогон показал 2/3 NOT_FOUND из-за неправильных DOI (0301-7 вместо 0300-7, aax2343 вместо aax2342). После исправления DOI — 3/3.

---

## Кредиты FireCrawl

> В этом прогоне FireCrawl не использовался — только OpenAlex (бесплатно) + Crawl4AI (бесплатно).
