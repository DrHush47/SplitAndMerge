# docx-protocol.md — Протокол работы с .docx через python-docx

> **Основной инструмент:** `python-docx` (подтверждён A/B тестом: в 1500× быстрее OfficeCLI, 80% правок с первой попытки vs 40%).
> **Каскад фактчекинга:** см. [`knowledge.md`](knowledge.md) — проверка DOI, URL, веб-фактов.
> **OfficeCLI:** резервный инструмент (обычно не установлен; добавляется в проект при необходимости специальных операций вроде `--find` через границы runs).

---

## 1. Главные правила (пять штук, коротко)

### 1.1 Сначала разведка, потом правки
Перед первой правкой — прочитать документ через `python-docx`: количество параграфов, таблиц, структура.

```python
from docx import Document
doc = Document("файл.docx")
for i, p in enumerate(doc.paragraphs):
    print(f"P{i}: {p.text[:120]}")
print(f"Tables: {len(doc.tables)}")
```

### 1.2 Stable-ID через индексы и текстовые якоря
При вставке/удалении параграфов индексы сдвигаются. Используй:
- Поиск по `p.text.startswith("...")` для нахождения якоря
- `_element.addprevious()` / `_element.addnext()` для вставки относительно найденного параграфа
- Итерацию `enumerate()` вместо хардкода индексов

### 1.3 Один инструмент на задачу
- **Основной инструмент:** `python-docx` (один скрипт, все правки за 0.01 сек)
- **Навык `hush-docx`:** используется FreeBuff для рутинных механических правок. Содержит готовые хелперы (`insert_heading_before`, `renumber_references`, `replace_cross_run_in_cell` и др.), проверенные на 6 документах (10/10 правок, 0.065 сек в среднем). Покрывает: глобальное форматирование, вставку заголовков, замену в ячейках таблиц, перенумерацию ссылок, расшифровку аббревиатур, вставку в конец документа, удаление trailing empty paragraphs.
- **Резервный (если установлен):** OfficeCLI — только для `--find` через границы runs без написания кода
- **Микс «python-docx + OfficeCLI»** — антипаттерн. Выбирай один.

### 1.4 Длинные тексты — через Python-переменные, не через shell
Любой текст >50 символов с кириллицей, кавычками `«»`, `$`, `\n` — передавай через Python-переменные внутри скрипта. Shell-escape ненадёжен.

### 1.5 Checkpoint — это предупреждение, не блок
Post-check через `python-docx` (перечитать файл после сохранения) — полезен для выявления потерянных правок. Но **не exit** при расхождении: печатаем WARN и продолжаем. Exit — только при потере данных (количество параграфов уменьшилось, таблица пропала, файл не открывается).

**Лимит итераций:** максимум 1 второй прогон скрипта для точечных правок. Если после 2-го прогона всё равно есть issues — доставлять как есть + список оставшихся проблем.

### 1.6 Проверка на дублирование перед вставкой (эмпирический finding)

**Проблема:** при отсутствии якоря FreeBuff использует fallback и **не проверяет, не создаст ли это дублирование**. Зафиксированный случай: ТЗ просило заменить «Методика исследования.» → «МАТЕРИАЛЫ И МЕТОДЫ», но такого inline-подзаголовка в исходнике не было. FreeBuff использовал fallback и вставил НОВЫЙ заголовок «МАТЕРИАЛЫ И МЕТОДЫ» — но в исходнике такой заголовок **уже существовал** как полноценный раздел. Результат: 2 заголовка подряд.

**Правило:** перед вставкой заголовка или текстового блока — проверить, не существует ли уже такой же или похожий:

```python
def insert_heading_safe(doc, anchor_text, heading_text):
    # 1. Проверка дублирования
    for i, p in enumerate(doc.paragraphs):
        if heading_text.strip() in p.text:
            print(f"WARN: заголовок '{heading_text}' уже существует в P{i}")
            return False
    # 2. Если не существует — вставить
    _, anchor = find_para(doc, text_startswith=anchor_text)
    if anchor is None:
        print(f"WARN: якорь '{anchor_text}' не найден")
        return False
    # ... (логика вставки)
    return True
```

### 1.7 Fallback без проверки контекста — антипаттерн

Если ТЗ содержит якорь, которого нет в документе (например, «замени X на Y» — а X не существует), **не выполнять fallback механически**. Возможные варианты:
1. Сообщить о проблеме и пропустить правку
2. Поискать похожий якорь (с подтверждением через WARN)
3. **Обязательно** проверить дублирование перед вставкой замены

Не использовать `find_para(text_startswith=fallback_anchor)` без явного WARN в лог.

### 1.8 Валидация regex для двузначных номеров

При проверке нумерации (например, списка литературы) — **использовать regex `^\d+\.\s`**, не сравнение подстрок `txt[1:3] == ". "`. Последний не ловит двузначные номера (10, 11, ..., 27).

```python
import re
# ПЛОХО — не ловит двузначные
if txt[1:3] == ". ":
    numbered += 1

# ХОРОШО — regex
if re.match(r'^\d+\.\s', txt):
    numbered += 1
```

### 1.9 Unicode / кодировка — обязательно (эмпирический finding из сессий)

В сессиях на Windows были частые `UnicodeEncodeError: 'charmap' codec can't encode character` при выводе кириллицы в консоль (cp1251 по умолчанию). Чтобы не терять вывод и не падать на печати:

**1. В начале каждого Python-скрипта — принудительно UTF-8 на stdout/stderr:**

```python
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
```

Альтернатива (Python 3.7+):
```python
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
```

**2. В bash-командах с кириллическими именами файлов — явно указать `PYTHONUTF8=1`:**

```bash
PYTHONUTF8=1 python script.py
# или
PYTHONIOENCODING=utf-8 python script.py
```

**3. При чтении/записи файлов через `open()` — всегда явная кодировка:**

```python
# ПЛОХО — использует системную кодировку (cp1251 на Windows)
with open("file.txt") as f: ...
with open("file.txt", "w") as f: ...

# ХОРОШО — явно UTF-8
with open("file.txt", encoding='utf-8') as f: ...
with open("file.txt", "w", encoding='utf-8') as f: ...
```

**4. `python-docx` сам по себе работает с UTF-8 корректно** — Unicode-проблемы возникают только при:
- `print()` кириллического текста в консоль без переопределения stdout
- Чтении/записи вспомогательных `.txt` файлов без явной кодировки
- Передаче кириллических аргументов через `sys.argv` на Windows (используй `PYTHONUTF8=1`)

**5. `errors='replace'`** — НЕ падать на непредсказуемых символах, заменять на `?`. Лучше потерять символ в логе, чем уронить весь скрипт.

---

## 2. Быстрый путь (для большинства задач)

Если документ <500 параграфов и задача разовая — используйте этот путь. Не вызывайте thinker/code-reviewer до первой попытки.

```python
#!/usr/bin/env python3
"""Оркестратор правок .docx через python-docx."""
import shutil
from docx import Document
from docx.shared import Pt, Mm, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH

# 1. Копия исходника
shutil.copy("исходник.docx", "результат.docx")

# 2. Разведка
doc = Document("результат.docx")
for i, p in enumerate(doc.paragraphs):
    if p.text.strip():
        print(f"P{i}: {p.text[:100]}")

# 3. Все правки в одном скрипте (0.01 сек)
# ... (см. раздел 4 для шаблона)

# 4. Сохранение
doc.save("результат.docx")

# 5. Валидация (перечитать файл)
doc2 = Document("результат.docx")
print(f"Параграфов: {len(doc2.paragraphs)}, Таблиц: {len(doc2.tables)}")
```

**Время:** <5 минут на типовую задачу (написание скрипта + запуск). Один прогон.

---

## 3. Выбор инструмента по типу операции

| Операция | Инструмент | Почему |
|---|---|---|
| Глобальное форматирование (шрифт, поля, интервал) | `python-docx` | Итерация по `doc.paragraphs` + `doc.sections`. Для таблиц: `table.rows` → `row.cells` → `cell.paragraphs` |
| Вставка заголовка перед абзацем | `python-docx` | `p._element.addprevious(new_p._element)` — просто и быстро |
| Удаление подзаголовка из начала абзаца | `python-docx` | `p.text = p.text.replace("Подзаголовок. ", "")` — но см. §5.1 про cross-run |
| Замена текста в ячейке таблицы | `python-docx` | `table.rows[N].cells[M].paragraphs[0]` — прямой доступ. См. §5.1 для cross-run |
| Перенумерация списка (27 источников) | `python-docx` | Цикл `for i, p in enumerate(bib_paras): p.runs[0].text = f"{i+1}. " + ...` |
| Длинные вставки (TEXT-N фрагменты) | `python-docx` | `doc.add_paragraph(TEXT_N)` — без shell-escape |
| Создание нового документа с нуля | `python-docx` | Циклы, шаблоны |
| Cross-run --find (текст разбит по runs) | OfficeCLI (резерв) | Встроенный `--find` работает через границы runs автоматически |
| Трекаемые изменения, TOC, watermark | OfficeCLI (резерв) | Готовые операции (если установлен) |

---

## 4. Сценарий: Python-оркестратор (основной шаблон)

Рекомендуемый шаблон для задач на 5+ блоков правок.

```python
#!/usr/bin/env python3
"""Оркестратор правок .docx через python-docx."""
import shutil
from docx import Document
from docx.shared import Pt, Mm, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import copy

FILE = "результат.docx"
shutil.copy("исходник.docx", FILE)
doc = Document(FILE)

# =================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===================

def set_run_font(run, name="Times New Roman", size=12, bold=None, italic=None):
    """Установить шрифт run (включая cs и eastAsia)."""
    run.font.name = name
    run.font.size = Pt(size)
    if bold is not None: run.bold = bold
    if italic is not None: run.italic = italic
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn('w:rFonts'))
    if rFonts is None:
        rFonts = OxmlElement('w:rFonts')
        rPr.append(rFonts)
    for attr in ['w:ascii', 'w:hAnsi', 'w:cs', 'w:eastAsia']:
        rFonts.set(qn(attr), name)

def set_para_format(para, alignment=None, first_line_indent_cm=None,
                    line_spacing=None, bold=None, font_name="Times New Roman", font_size=12):
    """Установить формат параграфа и всех его runs."""
    if alignment is not None: para.alignment = alignment
    if first_line_indent_cm is not None:
        para.paragraph_format.first_line_indent = Cm(first_line_indent_cm)
    if line_spacing is not None:
        para.paragraph_format.line_spacing = line_spacing
    para.paragraph_format.space_after = Pt(0)
    para.paragraph_format.space_before = Pt(0)
    for run in para.runs:
        set_run_font(run, font_name, font_size, bold=bold)

def set_cell_format(cell, font_name="Times New Roman", font_size=12):
    """Установить шрифт во всех параграфах ячейки таблицы."""
    for para in cell.paragraphs:
        para.paragraph_format.first_line_indent = Cm(0)
        para.paragraph_format.line_spacing = 1.0
        para.paragraph_format.space_after = Pt(0)
        para.paragraph_format.space_before = Pt(0)
        for run in para.runs:
            set_run_font(run, font_name, font_size)

def find_para(doc, text_startswith=None, text_contains=None):
    """Найти параграф по началу текста или содержимому."""
    for i, p in enumerate(doc.paragraphs):
        if text_startswith and p.text.startswith(text_startswith):
            return i, p
        if text_contains and text_contains in p.text:
            return i, p
    return None, None

def insert_heading_before(doc, anchor_text, heading_text, check_duplicate=True):
    """Вставить заголовок (полужирный, по центру) перед абзацем-якорем.
    
    check_duplicate=True (по умолчанию) — проверить, не существует ли уже
    параграф с таким же текстом. Если да — WARN и не вставлять (см. §1.6).
    """
    # 1. Проверка дублирования (эмпирический finding §1.6)
    if check_duplicate:
        for i, p in enumerate(doc.paragraphs):
            if heading_text.strip() in p.text:
                print(f"WARN: заголовок '{heading_text}' уже существует в P{i} — пропускаем вставку")
                return False
    
    # 2. Поиск якоря
    _, anchor = find_para(doc, text_startswith=anchor_text)
    if anchor is None:
        print(f"WARN: якорь '{anchor_text}' не найден")
        return False
    
    # 3. Вставка через OxmlElement (полный контроль над pPr/rPr)
    new_p = OxmlElement('w:p')
    new_pPr = OxmlElement('w:pPr')
    jc = OxmlElement('w:jc'); jc.set(qn('w:val'), 'center'); new_pPr.append(jc)
    new_p.append(new_pPr)
    new_r = OxmlElement('w:r')
    new_rPr = OxmlElement('w:rPr')
    rFonts = OxmlElement('w:rFonts')
    for attr in ['w:ascii', 'w:hAnsi', 'w:cs', 'w:eastAsia']:
        rFonts.set(qn(attr), 'Times New Roman')
    new_rPr.append(rFonts)
    sz = OxmlElement('w:sz'); sz.set(qn('w:val'), '24'); new_rPr.append(sz)
    b = OxmlElement('w:b'); new_rPr.append(b)
    new_r.append(new_rPr)
    t = OxmlElement('w:t'); t.text = heading_text; new_r.append(t)
    new_p.append(new_r)
    anchor._element.addprevious(new_p)
    return True

def replace_cross_run_text(paragraph, old, new):
    """Заменить подстроку в параграфе с учётом cross-run разбивки.
    
    ВАЖНО: теряется форматирование runs[1:] — весь текст перезаписывается
    в runs[0] со стилем первого run. НЕ подходит для параграфов с разным
    форматированием частей текста (например, bold-подзаголовок + обычный текст).
    """
    if not paragraph.runs:
        return False
    full_text = paragraph.text
    if old not in full_text:
        return False
    new_text = full_text.replace(old, new)
    # Очистить все runs кроме первого, записать новый текст в первый run
    for run in paragraph.runs[1:]:
        run.text = ""
    paragraph.runs[0].text = new_text
    return True

def replace_cross_run_in_cell(cell, old, new):
    """Заменить подстроку во всех параграфах ячейки таблицы (cross-run aware)."""
    found = False
    for para in cell.paragraphs:
        if replace_cross_run_text(para, old, new):
            found = True
    return found

def renumber_references(doc, ref_start_pattern='ЛИТЕРАТУРА', ref_end_pattern='СВЕДЕНИЯ ОБ АВТОРАХ'):
    """Проставить нумерацию 1..N для параграфов между ref_start_pattern и ref_end_pattern.
    
    Особенности:
    - Очищает существующую нумерацию (regex r'^\s*\d+\.\s*') перед простановкой новой
    - Перезаписывает все runs кроме первого (аналогично replace_cross_run_text)
    - Пропускает пустые параграфы
    - Возвращает количество пронумерованных источников
    """
    import re
    ref_start = None
    for i, p in enumerate(doc.paragraphs):
        if p.text.strip() == ref_start_pattern:
            ref_start = i + 1
            break
    if ref_start is None:
        print(f"WARN: заголовок '{ref_start_pattern}' не найден")
        return 0
    
    n = 1
    for i in range(ref_start, len(doc.paragraphs)):
        p = doc.paragraphs[i]
        txt = p.text.strip()
        if not txt:
            continue
        if txt == ref_end_pattern:
            break
        # Убираем уже существующую нумерацию если есть
        cleaned = re.sub(r'^\s*\d+\.\s*', '', txt)
        new_text = f"{n}. {cleaned}"
        for run in p.runs[1:]:
            run.text = ""
        if p.runs:
            p.runs[0].text = new_text
        else:
            p.text = new_text
        n += 1
    return n - 1

# =================== БЛОКИ ПРАВОК ===================

# Блок A: Глобальное форматирование
for section in doc.sections:
    section.top_margin = Mm(25)
    section.bottom_margin = Mm(25)
    section.left_margin = Mm(25)
    section.right_margin = Mm(25)

for para in doc.paragraphs:
    set_para_format(para, line_spacing=1.0, first_line_indent_cm=1.25, font_size=12)

# Блок B: Заголовки
insert_heading_before(doc, "Сегодня внедрение", "ВВЕДЕНИЕ")

# Блок D: Правки в таблице
t = doc.tables[0]
for row in t.rows:
    for cell in row.cells:
        set_cell_format(cell)
# Замена текста в конкретной ячейке:
# cell = t.rows[6].cells[4]
# (см. §5.1 для cross-run замены)

# Блок G: Длинные вставки в конец
TEXT_4 = "Analysis of the implementation..."
doc.add_paragraph("TITLE OF THE ARTICLE IN ENGLISH")
doc.add_paragraph(TEXT_4)

# =================== СОХРАНЕНИЕ ===================
doc.save(FILE)
print(f"Сохранено: {FILE}")
```

---

## 5. Антипаттерны (что НЕ делать)

### 5.1 Cross-run текст (текст разбит по нескольким runs)
```python
# ПРОБЛЕМА: "Андрейченко" может быть разбит на r[0]="Андрей", r[1]="ченко"
# p.runs[0].text.replace("Андрейченко", "АНДРЕЙЧЕНКО") — НЕ сработает

# РЕШЕНИЕ: собрать полный текст, очистить runs, записать в r[0]
full_text = p.text
new_text = full_text.replace("Андрейченко", "АНДРЕЙЧЕНКО")
for run in p.runs[1:]:
    run.text = ""
p.runs[0].text = new_text
```

### 5.2 Exit на каждой мелкой неудаче
```python
# ПЛОХО — блокирует оставшиеся 5 блоков
if not found:
    sys.exit(1)

# ХОРОШО — warn и продолжение
if not found:
    print(f"WARN: '{anchor}' не найден, продолжаем", file=sys.stderr)
```

Только критичные ошибки вызывают exit:
- Файл не открывается после сохранения
- Количество параграфов уменьшилось
- Таблица пропала

### 5.3 Слишком много итераций
Если после 1-го прогона скрипта есть issues → правим скрипт и запускаем 2-й раз. Если после 2-го прогона всё равно есть issues → **доставлять файл как есть** + список оставшихся проблем. Не запускать 3-ю, 4-ю итерации.

### 5.4 Слишком много post-checks
Не запускайте проверки после каждого блока. Достаточно:
1. Прочитать файл после сохранения (1 раз в конце)
2. Проверить ключевые метрики (количество параграфов, таблиц, шрифты)

### 5.5 Забытый pPr/rPr при вставке параграфов
При ручном создании параграфов через OxmlElement — обязательно устанавливать `rPr` (шрифт, размер, bold). Без этого параграф унаследует стиль по умолчанию (часто не Times New Roman).

### 5.6 \xa0 (неразрывный пробел) после удаления подзаголовка
```python
# ПЛОХО — оставит \xa0 в начале
p.runs[0].text = p.runs[0].text.replace("Методика исследования.", "")
# результат: "\xa0Поиск научных публикаций..."

# ХОРОШО — очистка leading whitespace
import re
full_text = p.text
full_text = re.sub(r'^\s*Методика исследования\.\s*', '', full_text)
# перезаписать runs (см. §5.1)
```

### 5.6.1 Inline-подзаголовки — самый рискованный тип правки (эмпирический finding)

**Сценарий:** ТЗ просит заменить inline-подзаголовок (например, «Методика исследования. Поиск...» → «МАТЕРИАЛЫ И МЕТОДЫ\nПоиск...»). Но:
- Подзаголовка может не быть в исходнике (он уже вынесен в отдельный параграф)
- Замена `p.text.replace()` ломает структуру runs
- Сборка полного текста + перезапись в runs[0] теряет форматирование частей

**Рекомендация:** для замены inline-подзаголовков — **не использовать `p.text.replace()`**. Вместо этого:
1. Проверить, не существует ли уже отдельного параграфа с новым заголовком (§1.6)
2. Если существует — пропустить правку (или удалить только старый inline-подзаголовок из начала)
3. Если не существует — удалить старый параграф целиком + вставить 2 новых (заголовок + текст) через `insert_heading_before()`

### 5.6.2 Fallback при отсутствии якоря — обязательно с проверкой дублирования

Если ТЗ содержит якорь, которого нет в документе, fallback разрешён, но **только с явной проверкой дублирования** перед вставкой (см. §1.6 и `insert_heading_before(... check_duplicate=True)`).

### 5.6.3 Сравнение подстрок `txt[1:3] == ". "` не ловит двузначные номера

При валидации нумерации (1..27 источников) — использовать regex `^\d+\.\s`, не сравнение подстрок. Сравнение `txt[1:3]` для "10. Topol..." возвращает `"0."`, что не равно `". "` — номера 10-27 будут помечены как «не пронумерованы».

### 5.6.4 Cross-run замена теряет форматирование runs[1:]

`replace_cross_run_text()` перезаписывает весь текст в `runs[0]` со стилем первого run. Если в исходнике у параграфа было:
- `runs[0]`: bold-подзаголовок
- `runs[1]`: обычный текст

...то после замены весь текст станет bold. Для параграфов с разным форматированием — **не использовать**. Альтернатива: ручная логика с поиском нужного run и заменой только в нём.

### 5.7 Порядок нескольких add_paragraph в конец
`doc.add_paragraph()` добавляет в конец документа. При множественных вызовах порядок сохраняется (в отличие от OfficeCLI, где порядок мог нарушаться).

---

## 6. Минимальный pre-flight (3 пункта)

Перед первой правкой проверьте:

- [ ] Файл существует и **не открыт** в Word/LibreOffice
- [ ] `python-docx` установлен (`pip install python-docx`)
- [ ] Сделана копия исходника (для отката)

Всё. Остальные проверки — по необходимости.

---

## 7. Минимальная валидация (3 команды)

После всех правок:

```python
from docx import Document
doc = Document("результат.docx")
print(f"Параграфов: {len(doc.paragraphs)}")
print(f"Таблиц: {len(doc.tables)}")
# Проверить шрифты:
import zipfile, re
with zipfile.ZipFile("результат.docx") as z:
    xml = z.read('word/document.xml').decode('utf-8')
    fonts = set(re.findall(r'w:ascii="([^"]+)"', xml))
    print(f"Шрифты: {fonts}")
```

Если файл открывается и ключевые метрики совпадают — задача выполнена.

---

## 8. Когда звать sub-agents (редко)

### thinker-with-files-gemini
**Только если** после первой попытки 2+ блока не работают и вы не понимаете почему. Максимум 1 вызов на задачу.

### code-reviewer-minimax-m3
**Только если** вы написали сложный Python-оркестратор (>200 строк) с ветвлениями. Максимум 1 вызов. Для рутинных скриптов — не нужен.

### researcher-web / researcher-docs
Только для проверки фактов (названия журналов, брендов). Не для генерации основных данных.

---

## 9. Когда НЕ звать sub-agents (почти всегда)

- Разведка документа — делается `python-docx` напрямую
- Составление плана — делается в голове LLM
- Проверка результата — делается перечитыванием файла через `python-docx`

Если за задачу вы звали thinker/code-reviewer больше 2 раз суммарно — вы over-engineering.

---

## 10. Принципы завершения

### 10.1 Completion-First
Доставить 90% результата за 5 минут лучше, чем 100% за 30 минут. Если после 2 итераций есть рабочий файл с мелкими недочётами — доставьте его + список оставшихся правок.

### 10.2 Не зацикливаться на идеальности
Если 1-2 post-check показывают расхождения, но файл открывается и основные правки на месте — доставляйте.

### 10.3 Один прогон лучше пяти идеальных
Запустить скрипт, увидеть частичный результат, исправить, запустить снова — быстрее, чем 3 часа планировать.

---

## 11. TL;DR (выучить наизусть)

1. **Разведка:** прочитать документ через `python-docx` (параграфы, таблицы, структура).
2. **Инструмент:** `python-docx` — основной (0.01 сек, один скрипт). OfficeCLI — резерв (если установлен).
3. **План:** один Python-скрипт со всеми правками. Длинные тексты — в Python-переменных.
4. **Исполнение:** запустить скрипт через `basher`. Один прогон.
5. **Валидация:** перечитать файл через `python-docx`. Проверить параграфы, таблицы, шрифты.
6. **Готово.** Не углубляйтесь в pre/post-check для каждой операции.

**Главное:** надёжность через простоту. Один Python-скрипт, исполненный за 0.01 сек, лучше 8 CLI-команд за 20 секунд.

---

## 12. Сводка: что изменилось по сравнению с версией 1

| Параметр | v1 (OfficeCLI) | v2 (эта, python-docx) |
|---|---|---|
| Основной инструмент | OfficeCLI (CLI-команды) | **python-docx** (Python-скрипт) |
| Скорость | ~15-20 сек на 5 правок | **0.013 сек** на 5 правок |
| Правок с первой попытки | 40% (2/5) | **80%** (4/5) |
| Silent failures | Да (без --json) | **Редко** (только на fallback-сценариях, см. §1.6, §5.6.1) |
| Разведка | Обязательна (get, help, query) | **Не обязательна** (итерация по .paragraphs) |
| Cross-run --find | Встроенный | Ручная логика (§5.1) |
| Объём | 1107 строк (v1 оригинал) | ~350 строк |
| Этапов | 5 с контрольными точками | 3 (разведка → скрипт → валидация) |
| Code-reviewer | до 19 вызовов | максимум 1, опционально |
| Принципы | 5 обязательных | 5 + Completion-First + 3 эмпирических (§1.6-1.8) |

**Философия v2:** `python-docx` — основной инструмент (доказано A/B тестом). OfficeCLI — резерв для специфичных операций (обычно не установлен).

---

## 13. Эмпирические findings (от теста 8 правок, 2026-07-14)

Тест 8 правок разной сложности через FreeBuff + python-docx. Результат: 7/8 правок прошли с первого прогона, 1 silent failure (ПРАВКА 6).

### 13.1 Стратегии, надёжные с первого прогона

| Операция | Подход | Статус |
|---|---|---|
| Вставка заголовка перед абзацем | `OxmlElement('w:p')` + `addprevious()` + полный `pPr/rPr` | ✅ Надёжно |
| Добавление run в конец параграфа | `paragraph.add_run(text)` + наследование стиля от `runs[0]` | ✅ Надёжно |
| Замена в ячейке таблицы (cross-run) | `replace_cross_run_in_cell()` — сборка полного текста + перезапись в `runs[0]` | ✅ Надёжно (но теряет форматирование runs[1:]) |
| Поля страницы | `section.top_margin = Mm(N)` | ✅ Надёжно |
| Установка italic/bold | `for run in p.runs: run.italic = True` | ✅ Надёжно |
| Вставка в конец документа | `doc.add_paragraph(text)` | ✅ Надёжно |
| Нумерация списка | `enumerate()` + regex clean `^\s*\d+\.\s*` | ✅ Надёжно |

### 13.2 Стратегии, требующие особого внимания

| Операция | Подход | Риск |
|---|---|---|
| Замена inline-подзаголовка | `p.text.replace()` + разбиение на runs | ❌ Высокий риск silent failure (§5.6.1) |
| Fallback при отсутствии якоря | Автоматический поиск похожего якоря | ⚠️ Средний риск — обязательна проверка дублирования (§1.6) |
| Cross-run замена с разным форматированием | `replace_cross_run_text()` | ⚠️ Теряет форматирование runs[1:] (§5.6.4) |

### 13.3 Типы silent failures (что НЕ ловит самоотчёт FreeBuff)

1. **Дублирование заголовков** — fallback сработал, но создал копию существующего заголовка (§1.6)
2. **Потеря форматирования** — cross-run замена перезаписала runs[0], потеряны bold/italic из runs[1:] (§5.6.4)
3. **Ложная нумерация через сравнение подстрок** — `txt[1:3] == ". "` пропускает двузначные номера (§1.8, §5.6.3)

**Решение:** программная валидация Рецензентом (Z.AI) после каждого прогона FreeBuff — обязательна. Самоотчёт FreeBuff («OK, fallback сработал») **недостоверен** без независимой проверки.

### 13.4 Что FreeBuff делает хорошо (новые тактические приёмы)

1. **OxmlElement для вставки параграфов** — даёт полный контроль над `pPr`, `rPr`, `rFonts`, `sz`, `b` одновременно. Необычный приём (обычно используют `add_paragraph()`), но даёт более надёжный результат.
2. **Очистка существующей нумерации перед простановкой новой** — `re.sub(r'^\s*\d+\.\s*', '', txt)` — защита от двойной нумерации.
3. **Fallback через `find_para(text_startswith=...)`** — корректный поиск похожего якоря, но нужен WARN при использовании.

### 13.5 Время выполнения

- 8 правок через python-docx: ~0.01-0.05 сек (замер через `time.time()`)
- Это в 1500× быстрее OfficeCLI и в ~10000× быстрее ручной правки

### 13.6 Итоговый вердикт по тесту

**7/8 правок с первого прогона** — соответствует заявленным 80% (4/5) в сводке §12. Оставшийся 1 silent failure (ПРАВКА 6) — это тип сложной правки (замена inline-подзаголовка), которая требует **ручной валидации Рецензентом**. Для рутинных правок (поля, шрифты, вставка, нумерация) — python-docx + FreeBuff полностью надёжен.
