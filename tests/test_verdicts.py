"""Тесты pipeline/verdicts.py — единая модель вердикта.

Покрывают: маппинг статусов OpenAlex → вердикт, evidence-states,
распознавание маркеров блокировки, сериализацию VerdictRecord/write_json.
"""

import json

import pytest

from pipeline.verdicts import (
    Verdict, VerdictRecord, verdict_from_openalex, classify_retrieval,
    detect_blocked, write_json,
    RETRIEVED_OK, BLOCKED, FAILED, SKIPPED,
)


# --- маппинг статусов OpenAlex → вердикт ---

@pytest.mark.parametrize("status,expected", [
    ("CONFIRMED", Verdict.CONFIRMED),
    ("MISMATCH", Verdict.REFUTED),
    ("ERROR", Verdict.UNCERTAIN),
    ("SKIP", Verdict.UNCERTAIN),
    ("?неизвестный_статус?", Verdict.UNCERTAIN),  # консервативный fallback
])
def test_verdict_from_openalex(status, expected):
    assert verdict_from_openalex(status) is expected


def test_openalex_mismatch_leads_to_refuted_with_review_flag():
    # needs_review проставляет sam.py (run_cascade): MISMATCH → REFUTED, решение за человеком
    verdict = verdict_from_openalex("MISMATCH")
    assert verdict is Verdict.REFUTED
    rec = VerdictRecord(id="r1", fact="f", url="u", verdict=verdict,
                        reason="сверить с исходником вручную", needs_review=True)
    assert rec.to_dict()["verdict"] == "REFUTED"
    assert rec.to_dict()["needs_review"] is True


# --- evidence-states ---

def test_evidence_states_are_distinct():
    states = {RETRIEVED_OK, BLOCKED, FAILED, SKIPPED}
    assert len(states) == 4
    assert states == {"RETRIEVED_OK", "BLOCKED", "FAILED", "SKIPPED"}


# --- маркеры блокировки ---

@pytest.mark.parametrize("text", [
    "Just a moment... Cloudflare",
    "cloudflare check",
    "ip заблокирован",
    "Security Verification page",
    "access denied",
    "please solve the CAPTCHA",
    "Captcha required to continue",
])
def test_detect_blocked_true(text):
    assert detect_blocked(text) is True


@pytest.mark.parametrize("text", ["", None, "Normal article text about science", "   "])
def test_detect_blocked_false(text):
    assert detect_blocked(text) is False


# --- classify_retrieval ---

@pytest.mark.parametrize("text,error,expected", [
    ("Hello world", None, RETRIEVED_OK),
    ("Just a moment... cloudflare", None, BLOCKED),
    ("", "timeout after 30s", FAILED),     # ошибка важнее пустого текста
    ("", None, FAILED),                    # EMPTY
    (None, "NetworkError", FAILED),
])
def test_classify_retrieval(text, error, expected):
    assert classify_retrieval(text, error) == expected


# --- VerdictRecord.to_dict ---

def test_to_dict_keys_and_values():
    rec = VerdictRecord(
        id="ref01", fact="Факт", url="https://doi.org/x",
        verdict=Verdict.UNCERTAIN, reason="evidence собран, требуется анализ агентом",
        levels_tried=["0.5", "2"], level_results={"0.5": {"status": "ERROR"}},
        artifacts=["workspace/oa_ref01.txt", "workspace/crawl_ref01.txt"],
        needs_review=True,
    )
    d = rec.to_dict()
    assert set(d.keys()) == {"id", "fact", "url", "verdict", "reason",
                             "levels_tried", "level_results", "artifacts", "needs_review"}
    assert d["verdict"] == "UNCERTAIN"
    assert d["levels_tried"] == ["0.5", "2"]
    assert d["level_results"] == {"0.5": {"status": "ERROR"}}
    assert d["artifacts"] == ["workspace/oa_ref01.txt", "workspace/crawl_ref01.txt"]
    assert d["needs_review"] is True


def test_needs_review_default_false():
    rec = VerdictRecord(id="r", fact="f", url="u", verdict=Verdict.CONFIRMED, reason="ok")
    assert rec.to_dict()["needs_review"] is False


# --- write_json ---

def test_write_json_utf8_cyrillic_as_is(tmp_path):
    out = tmp_path / "nested" / "verdicts.json"   # проверка создания родительских каталогов
    rec = VerdictRecord(id="ref01", fact="Факт с кириллицей", url="https://x",
                        verdict=Verdict.CONFIRMED, reason="OpenAlex CONFIRMED — DOI подтверждён")
    write_json([rec], out)

    assert out.is_file()
    raw = out.read_bytes()
    # кириллица хранится как есть (ensure_ascii=False), без \u-эскейпов
    assert b"\xe2\x80\x94" in raw or "—".encode("utf-8") in raw  # em-dash в reason
    text = raw.decode("utf-8")
    assert "Факт с кириллицей" in text
    assert "\\u" not in text

    data = json.loads(text)
    assert data[0]["verdict"] == "CONFIRMED"
    assert data[0]["reason"] == "OpenAlex CONFIRMED — DOI подтверждён"
