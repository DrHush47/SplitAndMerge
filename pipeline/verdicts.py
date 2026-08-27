#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verdicts.py — единая модель вердикта факт-чекера (Роль 5).

Словарь вердиктов РОВНО как в pipeline/docs/cascade.md, никаких новых слов:
    CONFIRMED — факт подтверждён (есть прямая цитата и URL источника)
    REFUTED   — факт опровергнут
    UNCERTAIN — подтверждение не найдено; НИКОГДА не выдумывать подтверждения
    BLOCKED   — источник заблокирован (ip заблокирован / cloudflare /
                security verification) — помечать BLOCKED, а не CONFIRMED

Evidence-states (НЕ вердикты, только статусы извлечения внутри level_results):
    RETRIEVED_OK / BLOCKED / FAILED / SKIPPED
    Успешное извлечение текста (SUCCESS: True) НЕ превращается в CONFIRMED —
    подтверждение даёт только программная проверка (OpenAlex кросс-чек)
    или человек/агент.

Матрица автоматических вердиктов (консервативная — в духе
«НИКОГДА не выдумывать подтверждения»):
  - OpenAlex CONFIRMED                     → CONFIRMED (эскалации не нужны)
  - OpenAlex MISMATCH                      → REFUTED (needs_review=True: рекомендация
                                              «сверить с исходником вручную»)
  - все попытки краула завершились BLOCKED → BLOCKED (+ рекомендация: «Ур.4 FireCrawl
                                              платно ИЛИ Ур.5 человек»; FireCrawl НЕ вызывается)
  - всё остальное                          → UNCERTAIN (reason различает:
                                              «evidence собран, требуется анализ агентом» /
                                              «требуется researcher-web, Ур.1»)
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


# ---------------------------------------------------------------------------
# Канонические вердикты (cascade.md) — ЕДИНСТВЕННЫЙ словарь вердиктов
# ---------------------------------------------------------------------------

class Verdict(Enum):
    CONFIRMED = "CONFIRMED"
    REFUTED = "REFUTED"
    UNCERTAIN = "UNCERTAIN"
    BLOCKED = "BLOCKED"


# ---------------------------------------------------------------------------
# Evidence-states — статусы извлечения для краулер-уровней (НЕ вердикты)
# ---------------------------------------------------------------------------

RETRIEVED_OK = "RETRIEVED_OK"
BLOCKED = "BLOCKED"      # маркер блокировки в полученном тексте
FAILED = "FAILED"        # ошибка/таймаут/пустой контент
SKIPPED = "SKIPPED"      # попытка не выполнялась

# Маркеры блокировки — case-insensitive подстроки в полученном тексте
BLOCK_MARKERS = (
    "cloudflare",
    "ip заблокирован",
    "security verification",
    "access denied",
    "captcha",
)


def detect_blocked(text):
    """True, если текст содержит маркер блокировки (case-insensitive подстрока)."""
    if not text:
        return False
    low = text.lower()
    return any(m in low for m in BLOCK_MARKERS)


def classify_retrieval(text, error=None):
    """Классифицировать результат извлечения в evidence-state.

    Приоритет: ошибка → FAILED; маркеры блокировки → BLOCKED;
    непустой текст → RETRIEVED_OK; пустой текст → FAILED (EMPTY).
    """
    if error:
        return FAILED
    if detect_blocked(text):
        return BLOCKED
    if text and text.strip():
        return RETRIEVED_OK
    return FAILED


# ---------------------------------------------------------------------------
# Отображение статусов OpenAlex → вердикт
# ---------------------------------------------------------------------------

_OPENALEX_TO_VERDICT = {
    "CONFIRMED": Verdict.CONFIRMED,
    "MISMATCH": Verdict.REFUTED,
    "ERROR": Verdict.UNCERTAIN,
    "SKIP": Verdict.UNCERTAIN,
}


def verdict_from_openalex(status):
    """OpenAlex-статус (CONFIRMED/MISMATCH/ERROR/SKIP) → канонический вердикт.

    Неизвестный статус → UNCERTAIN (консервативно).
    """
    return _OPENALEX_TO_VERDICT.get(status, Verdict.UNCERTAIN)


# ---------------------------------------------------------------------------
# Запись вердикта
# ---------------------------------------------------------------------------

@dataclass
class VerdictRecord:
    """Итог по одной цели: вердикт + путь эскалации + evidence по уровням.

    levels_tried: list[str] — какие уровни каскада реально отработали
                  (например ["0.5", "2", "3"]).
    level_results: dict[str, dict] — evidence по каждому уровню, например
                  {"0.5": {"status": "MISMATCH"}, "3": {"retrieval": "BLOCKED"}}.
    artifacts: list[str] — относительные пути к workspace-файлам.
    needs_review: True — решение за человеком/агентом (не финальный ответ).
    """
    id: str
    fact: str
    url: str
    verdict: Verdict
    reason: str
    levels_tried: list = field(default_factory=list)
    level_results: dict = field(default_factory=dict)
    artifacts: list = field(default_factory=list)
    needs_review: bool = False

    def to_dict(self):
        verdict_value = self.verdict.value if isinstance(self.verdict, Verdict) else str(self.verdict)
        return {
            "id": self.id,
            "fact": self.fact,
            "url": self.url,
            "verdict": verdict_value,
            "reason": self.reason,
            "levels_tried": list(self.levels_tried),
            "level_results": self.level_results,
            "artifacts": list(self.artifacts),
            "needs_review": self.needs_review,
        }


def write_json(records, path):
    """Сериализовать записи в JSON (UTF-8, ensure_ascii=False, indent=2)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump([r.to_dict() for r in records], f, ensure_ascii=False, indent=2)
