import hashlib
import logging

from langmem import create_memory_manager

from llm_setup import llm
from memory_schemas import FailureLesson, LearnedLesson
from memory_store import MemoryCollection

logger = logging.getLogger(__name__)

_LEARN_INSTRUCTIONS = (
    "Extract exactly one LearnedLesson memory that captures the reusable, durable "
    "fact or conclusion from this accepted answer. Do not store the raw Q&A "
    "verbatim — distill it into something worth recalling for a future question "
    "that is worded differently but touches the same topic."
)
_FAILURE_INSTRUCTIONS = (
    "Extract exactly one FailureLesson memory that captures why the rejected "
    "answer was wrong or unhelpful, and what should be done differently the next "
    "time a similar question is asked. Treat the user's feedback as the source of "
    "truth for what went wrong."
)

# Insert-only: this experiment doesn't exercise LangMem's update/delete
# consolidation behavior yet, matching the tutorial's simple first pass.
_learn_manager = create_memory_manager(
    llm,
    schemas=[LearnedLesson],
    instructions=_LEARN_INSTRUCTIONS,
    enable_inserts=True,
    enable_updates=False,
    enable_deletes=False,
)
_failure_manager = create_memory_manager(
    llm,
    schemas=[FailureLesson],
    instructions=_FAILURE_INSTRUCTIONS,
    enable_inserts=True,
    enable_updates=False,
    enable_deletes=False,
)


def _stable_id(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def record_accepted(query: str, answer: str, learned_qa: MemoryCollection) -> bool:
    """Distill an accepted answer into learned_qa via LangMem's memory manager."""
    conversation = [
        {"role": "user", "content": query},
        {"role": "assistant", "content": answer},
    ]
    extracted = _learn_manager.invoke({"messages": conversation, "max_steps": 1})

    stored_any = False
    for memory in extracted:
        if not isinstance(memory.content, LearnedLesson):
            continue
        lesson = memory.content
        text = f"Q: {lesson.question}\nLesson: {lesson.lesson}"
        stored = learned_qa.add(
            _stable_id(text),
            text,
            {
                "question": lesson.question,
                "lesson": lesson.lesson,
                "reason": lesson.reason,
                "source": "learned_qa",
                "original_query": query[:200],
            },
        )
        stored_any = stored_any or stored
    return stored_any


def record_rejected(query: str, answer: str, feedback: str, failure_lessons: MemoryCollection) -> bool:
    """Distill a rejected answer into failure_lessons via LangMem's memory manager."""
    conversation = [
        {"role": "user", "content": query},
        {"role": "assistant", "content": answer},
        {"role": "user", "content": f"This answer was rejected. Feedback: {feedback}"},
    ]
    extracted = _failure_manager.invoke({"messages": conversation, "max_steps": 1})

    stored_any = False
    for memory in extracted:
        if not isinstance(memory.content, FailureLesson):
            continue
        lesson = memory.content
        text = f"Q: {lesson.question}\nMistake: {lesson.mistake}\nGuidance: {lesson.guidance}"
        stored = failure_lessons.add(
            _stable_id(text),
            text,
            {
                "question": lesson.question,
                "mistake": lesson.mistake,
                "guidance": lesson.guidance,
                "reason": lesson.reason,
                "source": "failure_lessons",
                "original_query": query[:200],
            },
        )
        stored_any = stored_any or stored
    return stored_any
