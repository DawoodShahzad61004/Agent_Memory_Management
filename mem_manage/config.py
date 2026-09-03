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
# Log entries are split on a '## ' header line; a lookahead split keeps the
# delimiter attached to the block that follows it instead of eating it.
EPISODIC_BLOCK_SPLIT_PATTERN = re.compile(r"\n(?=## )")
# Header shape: 'DATE TIME SEP TAG...', e.g. '2026-08-29 12:48:55Z - requirements'.
EPISODIC_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%SZ"

# --- Entity extraction (importance.extract_entities) -------------------------
# Each alternative captures into its own group; exactly one group is
# non-None per match. Not an NLP model - a cheap, dependency-free heuristic
# tuned for code/CI-flavoured log text.
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
# Principle 6 (explicit choices outrank inferred preferences): an explicitly
# stated fact starts from a higher initial score, not just a slower decay.
EXPLICIT_PROVENANCE_BOOST = 0.2
# f_recency's exponential-decay half-life (paper's own maturation half-life;
# a starting point, not a settled constant - see Architecture.md's Formulae note).
RECENCY_HALF_LIFE_HOURS = 168.0
# f_frequency: two records count as "similar" (same recurring event) at or
# above this text-similarity ratio, regardless of tag.
FREQUENCY_SIMILARITY_THRESHOLD = 0.6
# f_outcome: deliberately short marker lists, not an NLP classifier - tuned
# for CI/agent run output (exit codes, test verbs), not general prose.
DEFAULT_SUCCESS_MARKERS = ("passed", "success", "resolved", "fixed", "works")
DEFAULT_FAILURE_MARKERS = ("failed", "error", "not recognized", "exit 1", "traceback")

# --- Passive decay (Architecture.md Formulae row 2) ---------------------------
# I(t) = I0 * e^(-lambda * t), t in hours since the record was last touched.
# Per hour; paper's calibration, ln(2)/lambda =~ 693h =~ 29-day half-life.
DECAY_LAMBDA_PER_HOUR = 0.001

# --- Embeddings / dedup-merge --------------------------------------------------
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_ENCODING_TIMEOUT_SECONDS = 30.0
# Near-duplicate cutoff for merging two durable memories - deliberately much
# stricter than FREQUENCY_SIMILARITY_THRESHOLD above: that one only measures
# "how novel is this", merging is destructive and must not fold together two
# memories that merely share a topic (that's the conflicting-versions case,
# which is meant to survive as separate records - see Architecture.md
# Principle 4).
MERGE_SIMILARITY_THRESHOLD = 0.90

# --- LLM: one local OpenAI-compatible endpoint, two roles ---------------------
# Same endpoint convention as memora_mini/config.py and Sample_Coding_Agent -
# repo-root .env, loaded by absolute path (ADR-006/ADR-023).
CUSTOM_API_BASE = os.getenv("CUSTOM_API_BASE", "")
CUSTOM_API_KEY = os.getenv("CUSTOM_API_KEY", "not-needed")
CUSTOM_API_MODEL_NAME = os.getenv("CUSTOM_API_MODEL_NAME", "llama-3.1-8b-instruct")
JUDGE_MODEL_NAME = os.getenv("JUDGE_MODEL_NAME", "Qwen/Qwen2.5-7B-Instruct")

MERGE_LLM_TEMPERATURE = 0.1
MERGE_LLM_MAX_TOKENS = 2048
JUDGE_LLM_TEMPERATURE = 0.0
JUDGE_LLM_MAX_TOKENS = 1024
# 0 on the LangChain client itself - services.llm_caller.llm_invoke is what
# actually retries, so the client must not also retry underneath it.
LLM_MAX_RETRIES = 0

# services.llm_caller's FIFO gate / adaptive cooldown. No measured value to
# copy from (the sibling project's own app_workflow/config.py wasn't carried
# over) - these are documented, reasonable starting points, not calibrated
# constants; verify before relying on them, same spirit as Architecture.md's
# own "verify before implementing" note on the paper's constants.
LLM_RATE_LIMIT_MAX_ATTEMPTS = 5
LLM_RATE_LIMIT_BACKOFF_BASE_SECONDS = 2.0
LLM_RATE_LIMIT_BACKOFF_MAX_SECONDS = 60.0
LLM_RATE_LIMIT_MAX_DELAY_SECONDS = 120.0
LLM_RESPONSE_TIMEOUT_SECONDS = 60.0
MIN_COOLDOWN_TIME = 0.0
MAX_COOLDOWN_TIME = 30.0
# Short-timeout reachability probe before a real run, mirroring
# memora_mini/llm.py's is_reachable() - this endpoint has a documented
# history of being unreachable (Bugs.md BUG-002, Status.md).
LLM_REACHABILITY_TIMEOUT_SECONDS = 5.0

# Feature flags for the dedup/merge step - both default on, but merge_group's
# deterministic union is always computed as the fallback regardless.
MERGE_LLM_ENABLED = True
MERGE_VALIDATION_ENABLED = True

# --- Consolidation / pruning ---------------------------------------------------
# Bottom-N% of durable memories, reranked by (decayed) importance, pruned
# each run. Matches the paper's own 20/60/20 promote/retain/prune bands
# (Research.md topic 10).
PRUNE_BOTTOM_PERCENT = 0.20

# --- Logging --------------------------------------------------------------------
DEFAULT_LOG_DIR = PACKAGE_ROOT / "run_logs"
