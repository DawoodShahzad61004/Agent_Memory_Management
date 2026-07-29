import logging

from config import MEMORY_SEARCH_K
from llm_caller import llm_invoke
from llm_setup import llm
from memory_store import MemoryCollection
from prompts import _GENERATE_ANSWER_PROMPT
from state import GraphState

logger = logging.getLogger(__name__)


def user_input_node(state: GraphState) -> dict:
    return {"user_input": (state["user_input"] or "").strip()}


def _build_context(learned_hits: list[dict], failure_hits: list[dict]) -> str:
    blocks = [f"[Source: learned_qa] {hit['content']}" for hit in learned_hits]
    blocks += [f"[Source: failure_lessons] {hit['content']}" for hit in failure_hits]
    return "\n\n".join(blocks)


def make_generate_answer_node(learned_qa: MemoryCollection, failure_lessons: MemoryCollection):
    """Closes over the two memory collections so the node stays a plain
    (state, config) -> dict callable, matching the LangGraph node signature."""

    def generate_answer_node(state: GraphState, config=None) -> dict:
        query = state["user_input"]

        learned_hits = learned_qa.search(query, k=MEMORY_SEARCH_K)
        failure_hits = failure_lessons.search(query, k=MEMORY_SEARCH_K)
        context = _build_context(learned_hits, failure_hits) or (
            "No prior lessons stored yet for this topic."
        )

        prompt = _GENERATE_ANSWER_PROMPT.format(query=query, context=context)
        result = llm_invoke(llm, [{"role": "user", "content": prompt}], caller_tag="GENERATE-ANSWER", config=config)

        if result.ok:
            answer = (result.content or "").strip()
        else:
            logger.error("[GENERATE_ANSWER] LLM call failed (%s): %s", result.error_kind, result.error_message)
            answer = ""

        return {"answer": answer}

    return generate_answer_node
