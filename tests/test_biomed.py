#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_biomed.py — тесты для модуля pipeline.biomed (Ур. 0.7 «BioMed Deep Check»).
"""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from pipeline.biomed.factcheck_biomed import (
    extract_pmid,
    extract_pmc,
    check_biomed_fact_match,
    lookup_pubmed_pmid,
    lookup_europepmc,
    save_biomed_result,
    batch_lookup_biomed,
)


# =================== ТЕСТЫ ИЗВЛЕЧЕНИЯ ИДЕНТИФИКАТОРОВ ===================

def test_extract_pmid_from_url():
    assert extract_pmid({"url": "https://pubmed.ncbi.nlm.nih.gov/35113657/", "expect": ""}) == "35113657"
    assert extract_pmid({"url": "http://ncbi.nlm.nih.gov/pubmed/12345678", "expect": ""}) == "12345678"
    assert extract_pmid({"url": "https://example.com/paper", "expect": ""}) is None


def test_extract_pmid_from_expect():
    assert extract_pmid({"url": "https://example.com", "expect": "PMID: 35113657"}) == "35113657"
    assert extract_pmid({"url": "https://example.com", "expect": "pmid 99887766, vol 2"}) == "99887766"
    assert extract_pmid({"url": "https://example.com", "expect": "PMID#11223344"}) == "11223344"


def test_extract_pmc_from_url():
    assert extract_pmc({"url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8912345/", "expect": ""}) == "PMC8912345"
    assert extract_pmc({"url": "https://europepmc.org/article/PMC/8912345", "expect": ""}) == "PMC8912345"


def test_extract_pmc_from_expect():
    assert extract_pmc({"url": "https://example.com", "expect": "PMCID: PMC8912345"}) == "PMC8912345"
    assert extract_pmc({"url": "https://example.com", "expect": "PMC 7654321"}) == "PMC7654321"


# =================== ТЕСТЫ КРОСС-ПРОВЕРКИ FACT vs METADATA ===================

def test_check_biomed_fact_match_author_hit():
    data = {
        "title": "Morphological analysis of cardiac tissue",
        "first_author": "Ivanov I.I.",
        "authors": ["Ivanov I.I.", "Petrov P.P."]
    }
    fact = "Иванов И.И. — Гистологическое строение миокарда при гипертрофии"
    # Транслит/латиница в фамилии
    data_lat = {
        "title": "Histological structure of myocardium",
        "first_author": "Ivanov I",
        "authors": ["Ivanov I"]
    }
    fact_lat = "Ivanov I. — Myocardial hypertrophy study"
    is_match, detail = check_biomed_fact_match(fact_lat, data_lat)
    assert is_match is True
    assert "author 'Ivanov' found in fact" in detail


def test_check_biomed_fact_match_title_overlap():
    data = {
        "title": "Epigenetic regulation of vascular remodeling in hypertension",
        "first_author": "Smith J",
        "authors": ["Smith J"]
    }
    fact = "Brown A. — Epigenetic regulation of vascular remodeling"
    is_match, detail = check_biomed_fact_match(fact, data)
    assert is_match is True
    assert "title overlap" in detail


def test_check_biomed_fact_match_mismatch():
    data = {
        "title": "Quantum dots in semiconductor physics",
        "first_author": "Kovacs L",
        "authors": ["Kovacs L"]
    }
    fact = "Smith J. — Histological staining protocols in liver fibrosis"
    is_match, detail = check_biomed_fact_match(fact, data)
    assert is_match is False
    assert "NOT in fact" in detail


# =================== ТЕСТЫ API LOOKUP (MOCK) ===================

@patch("urllib.request.urlopen")
def test_lookup_pubmed_pmid_success(mock_urlopen):
    sample_json = {
        "result": {
            "35113657": {
                "uid": "35113657",
                "title": "Targeted therapies in oncology",
                "source": "Nature Medicine",
                "pubdate": "2022 Mar",
                "volume": "28",
                "issue": "3",
                "pages": "450-460",
                "authors": [{"name": "Taylor B"}],
                "articleids": [{"idtype": "doi", "value": "10.1038/s41591-022-01234-x"}]
            }
        }
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(sample_json).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    data, error = lookup_pubmed_pmid("35113657")
    assert error is None
    assert data["pmid"] == "35113657"
    assert data["title"] == "Targeted therapies in oncology"
    assert data["first_author"] == "Taylor B"
    assert data["doi"] == "10.1038/s41591-022-01234-x"


@patch("urllib.request.urlopen")
def test_lookup_pubmed_pmid_not_found(mock_urlopen):
    sample_json = {"result": {}}
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(sample_json).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    data, error = lookup_pubmed_pmid("99999999")
    assert data is None
    assert error == "NOT_FOUND"


@patch("urllib.request.urlopen")
def test_lookup_europepmc_success(mock_urlopen):
    sample_json = {
        "resultList": {
            "result": [
                {
                    "pmid": "31234568",
                    "pmcid": "PMC6600000",
                    "title": "Single-cell RNA sequencing of human myocardium",
                    "authorString": "Wang X, Zhang Y, Liu Z",
                    "journalTitle": "Circulation",
                    "pubYear": "2020",
                    "journalVolume": "141",
                    "doi": "10.1161/CIRCULATIONAHA.119.043210"
                }
            ]
        }
    }
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(sample_json).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    mock_urlopen.return_value = mock_resp

    data, error = lookup_europepmc("31234568", is_pmc=False)
    assert error is None
    assert data["title"] == "Single-cell RNA sequencing of human myocardium"
    assert data["pmcid"] == "PMC6600000"
    assert data["first_author"] == "Wang X"


# =================== ТЕСТЫ СОХРАНЕНИЯ АРТЕФАКТОВ ===================

def test_save_biomed_result(tmp_path):
    target = {
        "id": "t1",
        "url": "https://pubmed.ncbi.nlm.nih.gov/35113657/",
        "fact": "Taylor B. — Targeted therapies in oncology",
        "expect": "PMID: 35113657"
    }
    data = {
        "title": "Targeted therapies in oncology",
        "authors": ["Taylor B"],
        "journal": "Nature Medicine",
        "pubdate": "2022",
        "volume": "28",
        "pages": "450-460",
        "doi": "10.1038/s41591-022-01234-x",
        "source_api": "NCBI E-utilities"
    }
    out_file = save_biomed_result(target, "35113657", "PMID", data, None, "CONFIRMED", "bm", tmp_path)
    assert out_file.is_file()
    content = out_file.read_text(encoding="utf-8")
    assert "PMID: 35113657" in content
    assert "STATUS: CONFIRMED" in content
    assert "TITLE: Targeted therapies in oncology" in content
    assert "API: NCBI E-utilities" in content
