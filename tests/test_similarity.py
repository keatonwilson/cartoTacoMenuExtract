"""Tests for description similarity (src/similarity.py). No network, DB or model."""

import hashlib

import numpy as np

from src import similarity as sim
from src.similarity import Spot


def test_description_hash_matches_sql():
    # cartoTaco public.description_hash('Mesquite grill', 'Long one'), checked in Postgres
    assert sim.description_hash("Mesquite grill", "Long one") == "9b2847e81645368fc26d32410b85fc8a"
    assert sim.description_hash("Late-night truck", None) == hashlib.md5(b"Late-night truck\n").hexdigest()


def test_identity_terms_and_cleaning():
    terms = sim.identity_terms("Tacos Apson", "1234 S 12th Ave, Tucson, AZ 85713")
    assert terms == ["Tacos Apson", "S 12th Ave", "12th Ave"]
    text = "Tacos Apson grills over mesquite on S 12th Ave; the 12th Ave line is long."
    assert sim.clean_text(text, terms) == "grills over mesquite on ; the line is long."


def test_cleaning_matches_whole_words_only():
    assert sim.clean_text("Elotes and a lot more", sim.identity_terms("Elote", None)) == "Elotes and a lot more"


def test_combine_weights_and_missing_halves():
    short = np.array([[1.0, 0.0], [1.0, 0.0]])
    long = np.array([[0.0, 1.0], [0.0, 1.0]])
    out = sim.combine(short, long, 0.3, np.array([True, False]), np.array([True, True]))
    assert np.allclose(np.linalg.norm(out, axis=1), 1)
    assert out[0][1] > out[0][0] > 0  # long weighs more
    assert np.allclose(out[1], [0, 1])  # no short: long alone


def test_similarity_pairs_are_unordered_cosines():
    vecs = np.array([[1.0, 0.0], [1.0, 1.0], [0.0, 2.0]])
    pairs = sim.similarity_pairs([5, 7, 9], vecs)
    assert [(p["a"], p["b"]) for p in pairs] == [(5, 7), (5, 9), (7, 9)]
    assert pairs[0]["score"] == round(1 / np.sqrt(2), 4)
    assert pairs[1]["score"] == 0.0


def test_neighbours_skip_closed_and_pending():
    spots = [Spot(1, "A", None, "a", "a"), Spot(2, "B", None, "b", "b", closed=True),
             Spot(3, "C", None, "c", "c", pending=True), Spot(4, "D", None, "d", "d")]
    pairs = [{"a": 1, "b": 2, "score": 0.9}, {"a": 1, "b": 3, "score": 0.8}, {"a": 1, "b": 4, "score": 0.5},
             {"a": 2, "b": 4, "score": 0.7}, {"a": 2, "b": 3, "score": 0.6}, {"a": 3, "b": 4, "score": 0.4}]
    near = sim.neighbours(spots, pairs)
    assert [o.est_id for o, _ in near[1]] == [4]
    assert [o.est_id for o, _ in near[2]] == [1, 4]  # a closed spot still gets neighbours
    assert "median" in sim.report(spots, pairs)


class _Q:
    def __init__(self, data):
        self.data = data

    def select(self, *_):
        return self

    def execute(self):
        return self


class _Client:
    def __init__(self, tables):
        self.tables = tables
        self.rpc_calls = []

    def table(self, name):
        return _Q(self.tables[name])

    def rpc(self, name, params):
        self.rpc_calls.append((name, params))
        return _Q(len(params["p_pairs"]))


def test_fetch_compute_write(monkeypatch):
    client = _Client({
        "sites": [
            {"est_id": 2, "name": "Bravo", "address": "1 E Main St, Tucson", "closed_at": None, "vetting_status": "vetted"},
            {"est_id": 1, "name": "Alfa", "address": None, "closed_at": "2026-01-01", "vetting_status": "vetted"},
            {"est_id": 3, "name": "Charlie", "address": None, "closed_at": None, "vetting_status": "vetted"},
        ],
        "descriptions": [
            {"est_id": 1, "short_descrip": "Mesquite", "long_descrip": "Grill"},
            {"est_id": 2, "short_descrip": "Bravo on Main St", "long_descrip": None},
            {"est_id": 3, "short_descrip": " ", "long_descrip": None},  # no text: skipped
        ],
    })
    spots = sim.fetch_spots(client)
    assert [s.est_id for s in spots] == [1, 2] and spots[0].closed

    seen = {}

    def fake_embed(texts, provider, model):
        seen["texts"] = texts
        return np.eye(len(texts))[:, :4] + 0.1

    monkeypatch.setattr(sim, "embed", fake_embed)
    result = sim.compute(spots, "fastembed")
    assert seen["texts"] == ["Mesquite", "on", "Grill", "-"]  # name + street stripped, empty slot padded
    assert result.model.startswith("fastembed:BAAI/")
    assert [(p["a"], p["b"]) for p in result.pairs] == [(1, 2)]

    assert sim.write(client, result) == 1
    name, params = client.rpc_calls[0]
    assert name == "replace_site_similarity"
    assert params["p_sources"] == [
        {"est_id": 1, "source_hash": sim.description_hash("Mesquite", "Grill")},
        {"est_id": 2, "source_hash": sim.description_hash("Bravo on Main St", None)},
    ]
