"""Sanity checks on the centralized constants/regex in mem_manage.config."""
from __future__ import annotations

import pytest

from mem_manage import config


def test_importance_weights_sum_to_one():
    assert sum(config.IMPORTANCE_WEIGHTS.values()) == pytest.approx(1.0)


def test_prune_bottom_percent_is_a_fraction():
    assert 0.0 < config.PRUNE_BOTTOM_PERCENT < 1.0


def test_enable_pruning_is_a_bool():
    assert isinstance(config.ENABLE_PRUNING, bool)


def test_min_prune_budget_is_positive():
    assert config.MIN_PRUNE_BUDGET > 0


def test_merge_similarity_threshold_is_a_fraction():
    assert 0.0 < config.MERGE_SIMILARITY_THRESHOLD <= 1.0


def test_frequency_similarity_threshold_is_a_fraction():
    assert 0.0 < config.FREQUENCY_SIMILARITY_THRESHOLD <= 1.0


def test_recency_half_life_is_positive():
    assert config.RECENCY_HALF_LIFE_HOURS > 0


def test_decay_lambda_is_positive():
    assert config.DECAY_LAMBDA_PER_HOUR > 0


def test_env_path_resolves_to_repo_root():
    assert config.ENV_PATH == config.REPO_ROOT / ".env"
    assert config.REPO_ROOT == config.PACKAGE_ROOT.parent


def test_episodic_block_split_pattern_splits_before_each_header():
    text = "## 2026-08-01 09:00:00Z - a\nbody one\n## 2026-08-02 09:00:00Z - b\nbody two"
    blocks = config.EPISODIC_BLOCK_SPLIT_PATTERN.split(text)
    assert len(blocks) == 2
    assert blocks[0].startswith("## 2026-08-01")
    assert blocks[1].startswith("## 2026-08-02")


class TestEntityPattern:
    """Each of ENTITY_PATTERN's four alternatives, checked in isolation."""

    def test_backtick_code_span(self):
        text = "see `foo.bar()` for details"
        found = {next(g for g in m.groups() if g) for m in config.ENTITY_PATTERN.finditer(text)}
        assert "foo.bar()" in found

    def test_camel_case(self):
        text = "the DurableMemory dataclass"
        found = {next(g for g in m.groups() if g) for m in config.ENTITY_PATTERN.finditer(text)}
        assert "DurableMemory" in found

    def test_ticket_style_tag(self):
        text = "fixed in T-001 after review"
        found = {next(g for g in m.groups() if g) for m in config.ENTITY_PATTERN.finditer(text)}
        assert "T-001" in found

    def test_dotted_path(self):
        text = "see mem_manage.config.py for the constant"
        found = {next(g for g in m.groups() if g) for m in config.ENTITY_PATTERN.finditer(text)}
        assert any("mem_manage.config.py" in entity for entity in found)

    def test_no_match_on_plain_lowercase_prose(self):
        text = "this sentence has no entities in it at all"
        assert list(config.ENTITY_PATTERN.finditer(text)) == []
