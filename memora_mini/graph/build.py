"""load_memory -> retrieve -> generate -> judge -> (retrieve | log_interaction) -> END"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from memora_mini.graph import nodes
from memora_mini.graph.state import RAGState


def build_graph():
    builder = StateGraph(RAGState)
    builder.add_node("load_memory", nodes.load_memory)
    builder.add_node("retrieve", nodes.retrieve)
    builder.add_node("generate", nodes.generate)
    builder.add_node("judge", nodes.judge)
    builder.add_node("log_interaction", nodes.log_interaction_node)

    builder.set_entry_point("load_memory")
    builder.add_edge("load_memory", "retrieve")
    builder.add_edge("retrieve", "generate")
    builder.add_edge("generate", "judge")
    builder.add_conditional_edges(
        "judge",
        nodes.route_after_judge,
        {"retrieve": "retrieve", "log_interaction": "log_interaction"},
    )
    builder.add_edge("log_interaction", END)
    return builder.compile()


def ask(store, question: str) -> dict:
    """Run one query end to end. Returns the final state."""
    return build_graph().invoke({"question": question, "store": store})
