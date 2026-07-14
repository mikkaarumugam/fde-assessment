"""Tests for the name-search relevance ranking. No network."""

from app.charity_client import _relevance


def rank(names, query):
    return sorted(names, key=lambda n: _relevance(n, query.lower()))


def test_exact_match_ranks_first():
    names = [
        "CANCER RESEARCH WALES",
        "CANCER RESEARCH AND GENETICS UK",
        "CANCER RESEARCH UK",
    ]
    assert rank(names, "cancer research uk")[0] == "CANCER RESEARCH UK"


def test_prefix_beats_mid_string_match():
    names = ["THE BRITISH HEART FOUNDATION FANS", "BRITISH HEART FOUNDATION"]
    assert rank(names, "british heart")[0] == "BRITISH HEART FOUNDATION"


def test_shorter_name_wins_a_prefix_tie():
    names = ["CANCER RESEARCH UK TRADING LIMITED", "CANCER RESEARCH UK"]
    assert rank(names, "cancer")[0] == "CANCER RESEARCH UK"


def test_whole_word_beats_bare_substring():
    names = ["INCANCEROUS GROWTHS TRUST", "MACMILLAN CANCER SUPPORT"]
    # 'cancer' is a standalone word in the second, only a substring in the first.
    assert rank(names, "cancer")[0] == "MACMILLAN CANCER SUPPORT"
