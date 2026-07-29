import os

from langchain_openai import ChatOpenAI

import config  # noqa: F401 — importing loads LangMem/.env as a side effect

# Single LLM instance for this simple graph: used both for generate_answer
# and (via learning.py) as the model backing LangMem's create_memory_manager.
llm = ChatOpenAI(
    base_url=os.getenv("CUSTOM_API_BASE"),
    api_key=os.getenv("CUSTOM_API_KEY"),
    model=os.getenv("CUSTOM_API_MODEL_NAME", "llama-3.1-8b-instruct"),
    temperature=0.1,
    max_tokens=2048,
    max_retries=0,
)