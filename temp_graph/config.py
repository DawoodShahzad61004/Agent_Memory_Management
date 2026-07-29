from pathlib import Path

from dotenv import load_dotenv

# This experiment's env file lives with the rest of the LangMem tutorial
# material (LangMem/.env), one level up — not duplicated here.
_PROJECT_ROOT = Path(__file__).resolve().parent
ENV_PATH = _PROJECT_ROOT.parent / "LangMem" / ".env"
load_dotenv(dotenv_path=ENV_PATH)

CHROMA_STORE_PATH = str(_PROJECT_ROOT / "chroma_store")
LEARNED_QA_COLLECTION = "learned_qa"
FAILURE_LESSONS_COLLECTION = "failure_lessons"
MEMORY_SEARCH_K = 4

# Mirrors ../../RAG-work/app_workflow/config.py defaults, trimmed to what
# embedding_manager.py and llm_caller.py actually read.
EMBEDDING_ENCODING_TIMEOUT_SECONDS = 5
LLM_RESPONSE_TIMEOUT_SECONDS = 150
LLM_RATE_LIMIT_MAX_ATTEMPTS = 3
LLM_RATE_LIMIT_BACKOFF_BASE_SECONDS = 1.0
LLM_RATE_LIMIT_BACKOFF_MAX_SECONDS = 30.0
LLM_RATE_LIMIT_MAX_DELAY_SECONDS = 1800.0
MIN_COOLDOWN_TIME = 0.0
MAX_COOLDOWN_TIME = 30.0
