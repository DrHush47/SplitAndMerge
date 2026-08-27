"""Общие настройки тестового ядра.

Модули конвейера импортируются ПАКЕТНО (from pipeline.verdicts import ...,
from pipeline.openalex.factcheck_openalex import ...), поэтому в sys.path
достаточно положить КОРЕНЬ репозитория (parents[1] от tests/conftest.py).

Защищённые factcheck-модули при импорте сами добавляют pipeline/ в sys.path
(собственные бутстрапы), поэтому их плоский `from common import ...` резолвится.
Пути считаем относительно этого файла.
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
