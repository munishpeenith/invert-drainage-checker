from pathlib import Path

import pytest
from pydantic import ValidationError

from rules.loader import PACK_DIR, RulePack, Source, for_regime, load_pack


def test_the_shipped_pack_loads(pack):
    assert pack.pack == "foul-gravity"
    assert pack.rules


def test_assert_is_read_from_the_reserved_yaml_key(pack):
    rule = next(r for r in pack.rules if r.id == "grad-min-adoption-150")
    assert rule.assert_ == {"gradient_1_in": {"lte": 150}}


def test_for_regime_includes_any_but_not_the_other_regime(pack):
    selected = for_regime(pack, "adoption")
    ids = {rule.id for rule in selected}
    assert "grad-min-adoption-150" in ids
    assert "internal-invert-continuity" in ids
    assert "grad-min-private-100" not in ids


def test_citation_names_document_edition_and_clause(pack):
    rule = next(r for r in pack.rules if r.id == "grad-min-adoption-150")
    citation = pack.citation(rule.source)
    assert "Design and Construction Guidance" in citation
    assert "B6.9" in citation


def test_internal_rules_cite_themselves_without_a_document(pack):
    rule = next(r for r in pack.rules if r.id == "internal-invert-continuity")
    assert pack.citation(rule.source) == "internal consistency"


def test_every_shipped_rule_has_a_clause(pack):
    for rule in pack.rules:
        assert rule.source.clause, rule.id


def test_a_rule_without_a_source_is_rejected():
    with pytest.raises(ValidationError):
        RulePack.model_validate(
            {
                "pack": "broken",
                "version": 1,
                "last_verified": "2026-09-30",
                "sources": {},
                "rules": [
                    {
                        "id": "no-source",
                        "regime": "any",
                        "applies_when": {},
                        "assert": {"diameter_mm": {"gte": 100}},
                        "severity": "fail",
                        "message": "x",
                    }
                ],
            }
        )
