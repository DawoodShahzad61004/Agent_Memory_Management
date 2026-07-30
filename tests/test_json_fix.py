from memora_mini.json_fix import parse_enum, parse_json, parse_list, strip_fences
from memora_mini.memory.classify import DEFAULT_VERDICT, VERDICTS
from memora_mini.memory.schemas import EpisodicMemory, FailureMemory


def test_strip_fences_and_surrounding_prose():
    assert strip_fences('```json\n[{"a": 1}]\n```') == '[{"a": 1}]'
    assert strip_fences('Here is the JSON you asked for: [{"a": 1}] Hope that helps!') == '[{"a": 1}]'


def test_parse_json_repairs_trailing_commas_and_single_quotes():
    assert parse_json('[{"a": 1,}]') == [{"a": 1}]
    assert parse_json("{'a': 1}") == {"a": 1}


def test_parse_list_validates_against_the_schema():
    raw = '[{"question": "What is ASD?", "answer": "Autism Spectrum Disorder.", "evidence_type": "observational", "confidence": 0.8}]'
    items = parse_list(raw, EpisodicMemory)
    assert len(items) == 1 and items[0].evidence_type == "observational"
    assert items[0].track == "learned_qa"


def test_parse_list_drops_bad_elements_but_keeps_good_ones():
    raw = ('[{"question": "q1", "answer": "a1", "evidence_type": "not_a_real_grade"},'
           ' {"question": "q2", "answer": "a2"}]')
    items = parse_list(raw, EpisodicMemory)
    assert [i.question for i in items] == ["q2"]


def test_parse_list_unwraps_a_wrapper_object():
    raw = '{"memories": [{"question": "q", "answer": "a"}]}'
    assert len(parse_list(raw, EpisodicMemory)) == 1


def test_parse_list_honours_limit():
    raw = '[{"question": "q1", "answer": "a"}, {"question": "q2", "answer": "a"}, {"question": "q3", "answer": "a"}]'
    assert len(parse_list(raw, EpisodicMemory, limit=2)) == 2


def test_parse_list_survives_total_garbage():
    assert parse_list("I'm sorry, I can't help with that.", EpisodicMemory) == []
    assert parse_list("", FailureMemory) == []


def test_parse_enum_extracts_a_single_token():
    assert parse_enum("CONTRADICTS", VERDICTS, DEFAULT_VERDICT) == "CONTRADICTS"
    assert parse_enum("The verdict is: refines.", VERDICTS, DEFAULT_VERDICT) == "REFINES"


def test_unparseable_classification_falls_back_to_unrelated():
    for junk in ("", "I think these are sort of similar?", "42", "```"):
        assert parse_enum(junk, VERDICTS, DEFAULT_VERDICT) == "UNRELATED"


def test_ambiguous_classification_takes_the_first_mention():
    assert parse_enum("DUPLICATE, or possibly REFINES", VERDICTS, DEFAULT_VERDICT) == "DUPLICATE"


def test_judge_enum_defaults_to_ok():
    assert parse_enum("blah", ("OK", "INSUFFICIENT"), "OK") == "OK"
    assert parse_enum("INSUFFICIENT", ("OK", "INSUFFICIENT"), "OK") == "INSUFFICIENT"
