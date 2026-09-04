"""All constants, feature flags, regex, and env loading for mem_manage.

Nothing else in the package reads os.environ directly, and no regex or
tunable threshold is defined inline anywhere else in the package — this is
the one place to look, and the one place to change any of them.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from dotenv import load_dotenv

PACKAGE_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_ROOT.parent
ENV_PATH = REPO_ROOT / ".env"
load_dotenv(dotenv_path=ENV_PATH)

# --- Episodic markdown parsing (importance.parse_episodic_md) ---------------
EPISODIC_BLOCK_SPLIT_PATTERN = re.compile(r"\n(?=## )")
# Header shape: 'DATE TIME SEP TAG...', e.g. '2026-08-29 12:48:55Z - requirements'.
EPISODIC_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%SZ"

# --- Entity extraction (importance.extract_entities) -------------------------
ENTITY_PATTERN = re.compile(
    r"`([^`]+)`"                                       # backtick code spans
    r"|\b([A-Z][a-zA-Z0-9]*(?:[A-Z][a-zA-Z0-9]*)+)\b"   # CamelCase / PascalCase
    r"|\b([A-Z]{1,6}-\d+)\b"                            # ticket-style tags, e.g. T-001
    r"|\b(\w+\.\w+(?:\.\w+)*)\b"                        # dotted filenames/paths
)

# --- Composite importance (Architecture.md Formulae row 1) -------------------
IMPORTANCE_WEIGHTS = {
    "recency": 0.25,
    "frequency": 0.25,
    "surprise": 0.20,
    "entity": 0.15,
    "outcome": 0.15,
}
# Principle 6 (explicit choices outrank inferred preferences)
EXPLICIT_PROVENANCE_BOOST = 0.2

RECENCY_HALF_LIFE_HOURS = 168.0
FREQUENCY_SIMILARITY_THRESHOLD = 0.6
DEFAULT_SUCCESS_MARKERS = ("passed", "success", "resolved", "fixed", "works")
DEFAULT_FAILURE_MARKERS = ("failed", "error", "not recognized", "exit 1", "traceback")

# --- Passive decay (Architecture.md Formulae row 2) ---------------------------
DECAY_LAMBDA_PER_HOUR = 0.001

# --- Embeddings / dedup-merge --------------------------------------------------
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_ENCODING_TIMEOUT_SECONDS = 30.0
MERGE_SIMILARITY_THRESHOLD = 0.60

# --- LLM: one local OpenAI-compatible endpoint, two roles ---------------------
CUSTOM_API_BASE = os.getenv("CUSTOM_API_BASE", "")
CUSTOM_API_KEY = os.getenv("CUSTOM_API_KEY", "")
CUSTOM_API_MODEL_NAME = os.getenv("CUSTOM_API_MODEL_NAME", "Qwen/Qwen2.5-7B-Instruct")
JUDGE_MODEL_NAME = os.getenv("JUDGE_MODEL_NAME", "Qwen/Qwen2.5-7B-Instruct")

MERGE_LLM_TEMPERATURE = 0.1
MERGE_LLM_MAX_TOKENS = 2048
JUDGE_LLM_TEMPERATURE = 0.0
JUDGE_LLM_MAX_TOKENS = 1024
LLM_MAX_RETRIES = 0

LLM_RATE_LIMIT_MAX_ATTEMPTS = 5
LLM_RATE_LIMIT_BACKOFF_BASE_SECONDS = 2.0
LLM_RATE_LIMIT_BACKOFF_MAX_SECONDS = 60.0
LLM_RATE_LIMIT_MAX_DELAY_SECONDS = 120.0
LLM_RESPONSE_TIMEOUT_SECONDS = 60.0
MIN_COOLDOWN_TIME = 0.0
MAX_COOLDOWN_TIME = 30.0

LLM_REACHABILITY_TIMEOUT_SECONDS = 5.0

MERGE_LLM_ENABLED = True
MERGE_VALIDATION_ENABLED = True

# --- Consolidation / pruning ---------------------------------------------------
PRUNE_BOTTOM_PERCENT = 0.20
ENABLE_PRUNING = True
# Below this many total characters across all consolidated memories, pruning
# is skipped outright - too small a corpus for "bottom PRUNE_BOTTOM_PERCENT"
# to be a meaningful signal.
MIN_PRUNE_BUDGET = 2_000

# --- Logging --------------------------------------------------------------------
DEFAULT_LOG_DIR = PACKAGE_ROOT / "run_logs"
