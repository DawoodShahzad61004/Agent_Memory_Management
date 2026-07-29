import chromadb
from langgraph.graph import END, START, StateGraph

from config import CHROMA_STORE_PATH, FAILURE_LESSONS_COLLECTION, LEARNED_QA_COLLECTION
from embedding_manager import EmbeddingManager
from memory_store import MemoryCollection
from nodes import make_generate_answer_node, user_input_node
from state import GraphState


def build_graph():
    """Wires the two-node graph (user_input -> generate_answer) and the two
    persistent ChromaDB memory collections it reads from.

    Returns (compiled_graph, learned_qa, failure_lessons) — the collections are
    returned alongside the graph so callers (main.py) can write accepted/
    rejected lessons back into the same collection handles via learning.py.
    """
    client = chromadb.PersistentClient(path=CHROMA_STORE_PATH)
    embedding_manager = EmbeddingManager()

    learned_qa = MemoryCollection(
        client,
        LEARNED_QA_COLLECTION,
        "Lessons distilled from answers the user accepted.",
        embedding_manager,
    )
    failure_lessons = MemoryCollection(
        client,
        FAILURE_LESSONS_COLLECTION,
        "Lessons distilled from answers the user rejected.",
        embedding_manager,
    )

    graph = StateGraph(GraphState)
    graph.add_node("user_input", user_input_node)
    graph.add_node("generate_answer", make_generate_answer_node(learned_qa, failure_lessons))

    graph.add_edge(START, "user_input")
    graph.add_edge("user_input", "generate_answer")
    graph.add_edge("generate_answer", END)

    return graph.compile(), learned_qa, failure_lessons
