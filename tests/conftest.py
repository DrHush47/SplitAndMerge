"""Общие настройки тестового ядра.

Импорты в pipeline-модулях плоские (from common import ..., from verdicts import ...),
поэтому тестам нужно добавить в sys.path корни pipeline и pipeline/openalex.
Пути считаем относительно этого файла (tests/conftest.py).
"""
import sys
from pathlib import Path

_PIPELINE = Path(__file__).resolve().parents[1] / "pipeline"

for _root in (_PIPELINE, _PIPELINE / "openalex"):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))
