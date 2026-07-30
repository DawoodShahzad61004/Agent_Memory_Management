"""All constants, feature flags and env loading for memora_mini.

Nothing else in the package reads os.environ directly.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent
ENV_PATH = REPO_ROOT / ".env"
load_dotenv(dotenv_path=ENV_PATH)

# --- LLM: one local OpenAI-compatible endpoint, every role ------------------
LLM_BASE_URL = os.getenv("CUSTOM_API_BASE", "")
LLM_API_KEY = os.getenv("CUSTOM_API_KEY", "not-needed")
LLM_MODEL = os.getenv("CUSTOM_API_MODEL_NAME", "llama-3.1-8b-instruct")
LLM_TEMPERATURE = 0.0
LLM_MAX_TOKENS = 1024
LLM_TIMEOUT_SECONDS = 120
LLM_MAX_ATTEMPTS = 3
LLM_BACKOFF_BASE_SECONDS = 1.0

# --- Embeddings: local sentence-transformers only, never a remote API -------
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

# --- Storage ----------------------------------------------------------------
CHROMA_PATH = str(PACKAGE_ROOT / "chroma_store")
DOCUMENTS_COLLECTION = "documents"
CORPUS_DIR = PACKAGE_ROOT / "corpus"
AUDIT_LOG_PATH = PACKAGE_ROOT / "memory_audit.jsonl"

# Chunking for ingest.py (character-based; the corpus is tiny by design).
CHUNK_SIZE = 700
CHUNK_OVERLAP = 100

# --- Namespaces -------------------------------------------------------------
# Single-user local system: the segmentation axis is corpus domain, not user id.
DOMAIN = "demo"

# --- Recall / strength scoring ----------------------------------------------
RECALL_LIMIT = 4
OVERFETCH_FACTOR = 3
STRENGTH_HIT_WEIGHT = 0.15  # w_hits in similarity * (1 + w*log1p(hits)) * decay
RECENCY_HALF_LIFE_DAYS = 14.0
RECENCY_FLOOR = 0.5  # decay never drops a memory below half its similarity
SIMILARITY_FLOOR = 0.15  # drop recall hits weaker than this before re-ranking

# --- Retrieval --------------------------------------------------------------
DOCUMENTS_TOP_K = 4
EPISODIC_TOP_K = 3
SEMANTIC_TOP_K = 3
MAX_FAILURE_INJECTIONS = 2
MAX_ITERATIONS = 2  # judge retry budget

# --- Memory formation -------------------------------------------------------
LEARN_EVERY_N = 5
MAX_CANDIDATES_PER_INTERACTION = 3
CLASSIFY_NEIGHBOURS = 3
MAX_OPS_PER_RUN = 20
PROTECTED_HIT_COUNT = 5
CONTRADICTION_STRIKES_REQUIRED = 2
PROCEDURAL_PROPOSAL_HITS = 3  # a failure theme this recurrent earns a prompt-rule proposal
DRY_RUN_MEMORY_OPS = True  # log proposed ops as JSON, write nothing
