"""Multi-scenario tests for mem_manage.importance: parsing, the five
composite-importance factors, their combination, and passive decay.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from mem_manage import config
from mem_manage.importance import (
    EpisodicRecord,
    build_entity_index,
    composite_importance,
    extract_entities,
    f_entity_salience,
    f_frequency,
    f_outcome,
    f_recency,
    f_surprise,
    parse_episodic_md,
    passive_decay,
)


# --- parse_episodic_md ---------------------------------------------------------


class TestParseEpisodicMd:
    def test_parses_multiple_well_formed_entries(self):
        text = (
            "## 2026-08-01 09:00:00Z - first\nfirst body\n"
            "## 2026-08-02 10:30:00Z - second\nsecond body"
        )
        records = parse_episodic_md(text)
        assert [r.tag for r in records] == ["first", "second"]
        assert [r.content for r in records] == ["first body", "second body"]
        assert records[0].timestamp == datetime(2026, 8, 1, 9, 0, 0, tzinfo=timezone.utc)

    def test_preserves_multi_word_tags(self):
        text = "## 2026-08-01 09:00:00Z - a multi word tag\nbody"
        records = parse_episodic_md(text)
        assert records[0].tag == "a multi word tag"

    def test_skips_header_with_too_few_tokens_without_crashing(self):
        text = "## just-one-token\nbody\n## 2026-08-01 09:00:00Z - ok\nok body"
        records = parse_episodic_md(text)
        assert len(records) == 1
        assert records[0].tag == "ok"

    def test_skips_header_with_unparseable_timestamp_without_crashing(self):
        text = "## 2026-08-02 99:99:99Z - bad\nbad body\n## 2026-08-01 09:00:00Z - ok\nok body"
        records = parse_episodic_md(text)
        assert len(records) == 1
        assert records[0].tag == "ok"

    def test_ignores_stray_preamble_before_first_header(self):
        text = "# Title\n\n## 2026-08-01 09:00:00Z - entry\nbody"
        records = parse_episodic_md(text)
        assert len(records) == 1
        assert records[0].tag == "entry"

    def test_empty_input_returns_empty_list(self):
        assert parse_episodic_md("") == []

    def test_raw_field_carries_the_full_original_block(self):
        text = "## 2026-08-01 09:00:00Z - tag\nbody line"
        records = parse_episodic_md(text)
        assert records[0].raw.startswith("## 2026-08-01")
        assert "body line" in records[0].raw

    def test_default_provenance_is_inferred(self):
        records = parse_episodic_md("## 2026-08-01 09:00:00Z - tag\nbody")
        assert records[0].provenance == "inferred"


# --- f_recency -------------------------------------------------------------------


class TestFRecency:
    def test_zero_age_scores_one(self, frozen_now):
        record = EpisodicRecord(frozen_now, "t", "content")
        assert f_recency(record, now=frozen_now) == pytest.approx(1.0)

    def test_half_life_age_scores_half(self, frozen_now):
        half_life = config.RECENCY_HALF_LIFE_HOURS
        record = EpisodicRecord(frozen_now - timedelta(hours=half_life), "t", "content")
        assert f_recency(record, now=frozen_now, half_life_hours=half_life) == pytest.approx(0.5)

    def test_two_half_lives_scores_quarter(self, frozen_now):
        half_life = config.RECENCY_HALF_LIFE_HOURS
        record = EpisodicRecord(frozen_now - timedelta(hours=2 * half_life), "t", "content")
        assert f_recency(record, now=frozen_now, half_life_hours=half_life) == pytest.approx(0.25)

    def test_future_timestamp_clamps_to_one_not_above(self, frozen_now):
        # Clock skew: the record is timestamped after `now`.
        record = EpisodicRecord(frozen_now + timedelta(hours=5), "t", "content")
        assert f_recency(record, now=frozen_now) == pytest.approx(1.0)


# --- f_frequency -----------------------------------------------------------------


class TestFFrequency:
    def test_novel_record_alone_in_corpus_scores_one(self, frozen_now):
        record = EpisodicRecord(frozen_now, "unique-tag", "nothing like this elsewhere")
        assert f_frequency(record, [record]) == pytest.approx(1.0)

    def test_same_tag_counts_as_similar_even_with_different_content(self, frozen_now):
        a = EpisodicRecord(frozen_now, "shared-tag", "totally different wording here")
        b = EpisodicRecord(frozen_now, "shared-tag", "nothing at all in common with the other")
        assert f_frequency(a, [a, b]) == pytest.approx(0.5)  # 1 similar -> 1/(1+1)

    def test_near_duplicate_content_counts_even_with_different_tags(self, frozen_now):
        a = EpisodicRecord(frozen_now, "tag-a", "This repo uses pytest fixtures for tests.")
        b = EpisodicRecord(frozen_now, "tag-b", "This repo uses pytest fixtures for all tests.")
        assert f_frequency(a, [a, b]) == pytest.approx(0.5)

    def test_unrelated_records_do_not_count(self, frozen_now):
        a = EpisodicRecord(frozen_now, "tag-a", "Deployed the staging server today.")
        b = EpisodicRecord(frozen_now, "tag-b", "Wrote the onboarding documentation.")
        assert f_frequency(a, [a, b]) == pytest.approx(1.0)

    def test_more_repeats_asymptotes_toward_zero(self, frozen_now):
        records = [EpisodicRecord(frozen_now, "same-tag", f"variant {i}") for i in range(5)]
        assert f_frequency(records[0], records) == pytest.approx(1.0 / 5)


# --- f_surprise --------------------------------------------------------------------


class TestFSurprise:
    def test_first_ever_record_is_maximally_surprising(self, frozen_now):
        record = EpisodicRecord(frozen_now, "t", "anything")
        assert f_surprise(record, [record]) == pytest.approx(1.0)

    def test_similar_earlier_record_lowers_surprise(self, frozen_now):
        earlier = EpisodicRecord(
            frozen_now - timedelta(days=1), "t", "This repo uses pytest fixtures for tests."
        )
        later = EpisodicRecord(
            frozen_now, "t", "This repo uses pytest fixtures for all tests."
        )
        surprise = f_surprise(later, [earlier, later])
        assert surprise < 0.5

    def test_similar_later_record_does_not_affect_the_earlier_ones_surprise(self, frozen_now):
        earlier = EpisodicRecord(frozen_now, "t", "a genuinely novel observation")
        later = EpisodicRecord(
            frozen_now + timedelta(days=1), "t", "a genuinely novel observation, repeated"
        )
        # `later` is highly similar to `earlier`, but it happened *after* -
        # it must not leak into how surprising `earlier` looked at the time.
        assert f_surprise(earlier, [earlier, later]) == pytest.approx(1.0)

    def test_dissimilar_prior_record_keeps_surprise_high(self, frozen_now):
        earlier = EpisodicRecord(frozen_now - timedelta(days=1), "t", "Deployed the server.")
        later = EpisodicRecord(frozen_now, "t", "Completely unrelated topic about documentation.")
        assert f_surprise(later, [earlier, later]) > 0.65


# --- entities: extract_entities / build_entity_index / f_entity_salience -----------


class TestEntities:
    def test_extract_entities_backtick_span(self):
        assert extract_entities("call `foo.bar()` here") == {"foo.bar()"}

    def test_extract_entities_camel_case(self):
        assert "DurableMemory" in extract_entities("the DurableMemory dataclass")

    def test_extract_entities_ticket_tag(self):
        assert "T-001" in extract_entities("fixed in T-001")

    def test_extract_entities_dotted_path(self):
        assert "mem_manage.config" in extract_entities("defined in mem_manage.config")

    def test_extract_entities_none_in_plain_prose(self):
        assert extract_entities("just a plain sentence") == set()

    def test_build_entity_index_scales_relative_to_peak_mention(self, frozen_now):
        corpus = [
            EpisodicRecord(frozen_now, "t", "`Foo` appears here"),
            EpisodicRecord(frozen_now, "t", "`Foo` appears again"),
            EpisodicRecord(frozen_now, "t", "`Bar` appears once"),
        ]
        index = build_entity_index(corpus)
        assert index["Foo"] == pytest.approx(1.0)  # the peak
        assert index["Bar"] == pytest.approx(0.5)

    def test_build_entity_index_empty_corpus_is_empty(self):
        assert build_entity_index([]) == {}

    def test_f_entity_salience_returns_max_of_referenced_entities(self, frozen_now):
        index = {"Foo": 1.0, "Bar": 0.2}
        record = EpisodicRecord(frozen_now, "t", "mentions both `Foo` and `Bar`")
        assert f_entity_salience(record, index) == pytest.approx(1.0)

    def test_f_entity_salience_no_entities_returns_default(self, frozen_now):
        record = EpisodicRecord(frozen_now, "t", "no entities in this sentence")
        assert f_entity_salience(record, {}, default=0.3) == pytest.approx(0.3)


# --- f_outcome -----------------------------------------------------------------------


class TestFOutcome:
    def test_pure_failure_scores_zero(self, frozen_now):
        record = EpisodicRecord(frozen_now, "t", "the build failed with a traceback")
        assert f_outcome(record) == pytest.approx(0.0)

    def test_pure_success_scores_one(self, frozen_now):
        record = EpisodicRecord(frozen_now, "t", "all tests passed after the fix")
        assert f_outcome(record) == pytest.approx(1.0)

    def test_mixed_signal_scores_below_neutral(self, frozen_now):
        record = EpisodicRecord(frozen_now, "t", "it failed at first but we fixed it and it works")
        assert f_outcome(record) == pytest.approx(0.4)

    def test_no_markers_scores_neutral(self, frozen_now):
        record = EpisodicRecord(frozen_now, "t", "just a plain observation about the code")
        assert f_outcome(record) == pytest.approx(0.5)


# --- composite_importance -------------------------------------------------------------


class TestCompositeImportance:
    def test_combines_the_five_weighted_factors(self, frozen_now):
        record = EpisodicRecord(frozen_now, "solo", "a plain observation with no markers")
        corpus = [record]
        entity_index = build_entity_index(corpus)
        expected = (
            config.IMPORTANCE_WEIGHTS["recency"] * f_recency(record, now=frozen_now)
            + config.IMPORTANCE_WEIGHTS["frequency"] * f_frequency(record, corpus)
            + config.IMPORTANCE_WEIGHTS["surprise"] * f_surprise(record, corpus)
            + config.IMPORTANCE_WEIGHTS["entity"] * f_entity_salience(record, entity_index)
            + config.IMPORTANCE_WEIGHTS["outcome"] * f_outcome(record)
        )
        actual = composite_importance(record, corpus, entity_index, now=frozen_now)
        assert actual == pytest.approx(expected)

    def test_explicit_provenance_scores_higher_than_inferred_otherwise_identical(self, frozen_now):
        content = "a plain observation with no markers"
        inferred = EpisodicRecord(frozen_now, "solo", content, provenance="inferred")
        explicit = EpisodicRecord(frozen_now, "solo", content, provenance="explicit")
        inferred_score = composite_importance(inferred, [inferred], {}, now=frozen_now)
        explicit_score = composite_importance(explicit, [explicit], {}, now=frozen_now)
        assert explicit_score == pytest.approx(inferred_score * (1 + config.EXPLICIT_PROVENANCE_BOOST))

    def test_explicit_boost_clamps_at_one(self, frozen_now):
        # All five factors maxed out: recency=1 (now==timestamp), frequency=1
        # (novel), surprise=1 (first-ever), outcome=1 (success marker),
        # entity=1 (mentions the corpus's single, peak-salience entity).
        record = EpisodicRecord(
            frozen_now, "solo", "the `Widget` build passed", provenance="explicit"
        )
        corpus = [record]
        entity_index = build_entity_index(corpus)
        score = composite_importance(record, corpus, entity_index, now=frozen_now)
        assert score == pytest.approx(1.0)

    def test_score_is_deterministic_given_a_fixed_now(self, frozen_now):
        record = EpisodicRecord(frozen_now, "t", "some content")
        corpus = [record]
        entity_index = build_entity_index(corpus)
        first = composite_importance(record, corpus, entity_index, now=frozen_now)
        second = composite_importance(record, corpus, entity_index, now=frozen_now)
        assert first == second


# --- passive_decay -----------------------------------------------------------------


class TestPassiveDecay:
    def test_zero_elapsed_time_leaves_importance_unchanged(self, frozen_now):
        assert passive_decay(0.8, frozen_now, now=frozen_now) == pytest.approx(0.8)

    def test_half_life_elapsed_halves_importance(self, frozen_now):
        half_life_hours = 693.0  # ln(2) / DECAY_LAMBDA_PER_HOUR (0.001 -> ~29 days)
        encoded_at = frozen_now - timedelta(hours=half_life_hours)
        result = passive_decay(0.8, encoded_at, now=frozen_now)
        assert result == pytest.approx(0.4, rel=1e-3)

    def test_last_accessed_at_resets_the_reference_point(self, frozen_now):
        encoded_long_ago = frozen_now - timedelta(days=365)
        recently_accessed = frozen_now - timedelta(hours=1)
        barely_decayed = passive_decay(
            0.8, encoded_long_ago, now=frozen_now, last_accessed_at=recently_accessed
        )
        never_reaccessed = passive_decay(0.8, encoded_long_ago, now=frozen_now)
        assert barely_decayed > never_reaccessed
        assert barely_decayed == pytest.approx(0.8, rel=1e-2)

    def test_clock_skew_does_not_grow_importance(self, frozen_now):
        # encoded_at slightly after `now` -> age must clamp to 0, not go negative.
        result = passive_decay(0.8, frozen_now + timedelta(hours=5), now=frozen_now)
        assert result == pytest.approx(0.8)

    def test_decay_never_goes_negative_or_exceeds_original(self, frozen_now):
        far_future = frozen_now + timedelta(days=10_000)
        result = passive_decay(0.8, frozen_now, now=far_future)
        assert 0.0 <= result <= 0.8
