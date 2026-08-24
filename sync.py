#!/usr/bin/env python3
"""
sync.py — Ручная синхронизация SplitAndMerge → GitHub (Python-вариант)
=============================================================================
Контекст (для FreeBuff-агента в новой сессии):
  - Проект: SplitAndMerge (редактура .docx + каскад фактчекинга)
  - Remote:  https://github.com/DrHush47/SplitAndMerge
  - Ветка:   main
  - Режим:   только push (pull — вручную, через `git pull origin main`)

Как вызвать:
  python sync.py                            # авто-сообщение: "sync: ЧЧ:ММ ДД.ММ.ГГГГ"
  python sync.py "обновил README и скрипты" # твой текст добавится к дате

Что делает:
  1. Проверяет: есть ли незакоммиченные изменения (`git status --porcelain`)
  2. Если изменений нет → выходит с сообщением «нечего пушить»
  3. Если есть → git add -A, коммит с датой/временем, push
=============================================================================
"""

import subprocess
import sys
from datetime import datetime


def run(cmd: list[str], exit_on_error: bool = True) -> str:
    """Запустить команду, вернуть stdout. При ошибке — выйти."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 and exit_on_error:
        print(f"[sync] Ошибка: {' '.join(cmd)}", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def main():
    # --- Шаг 1: проверить, есть ли изменения ------------------------------------
    changes = run(["git", "status", "--porcelain"])

    if not changes:
        print("[sync] Изменений нет — пушить нечего.")
        return

    print("[sync] Найдены изменения:")
    print(changes)
    print()

    # --- Шаг 2: добавить все файлы (с учётом .gitignore) ------------------------
    run(["git", "add", "-A"])

    # --- Шаг 3: коммит ----------------------------------------------------------
    now = datetime.now()
    timestamp = now.strftime("%d.%m.%Y %H:%M")  # формат: 25.08.2026 14:30
    description = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""

    if description:
        msg = f"sync: {timestamp} — {description}"
    else:
        msg = f"sync: {timestamp}"

    run(["git", "commit", "-m", msg])

    # --- Шаг 4: push на GitHub --------------------------------------------------
    run(["git", "push", "origin", "main"])

    print(f"\n[sync] Готово. Всё улетело на GitHub: {msg}")


if __name__ == "__main__":
    main()