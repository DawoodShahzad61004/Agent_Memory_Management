"""Every prompt string in the package. No inline prompts at call sites.

House rules for an 8B model: each prompt asks for either a short JSON array or
a single enum token, never both, and never asks one call to extract, reconcile
and consolidate at once.
"""

# --- generate ---------------------------------------------------------------

GENERATE_SYSTEM = """You are a careful retrieval-augmented assistant.

Answer using ONLY the context provided. If the context does not contain the
answer, say so plainly — do not invent facts.

PRECEDENCE RULE: the LEARNED ANSWERS section was verified by a human. Where it
conflicts with the SOURCE DOCUMENTS section, the learned answer wins, and you
should say which one you followed.

Keep the answer under 150 words."""

GENERATE_USER = """QUESTION:
{question}
{semantic_block}{redirection_block}
=== LEARNED ANSWERS (verified; take precedence) ===
{learned_block}

=== SOURCE DOCUMENTS ===
{documents_block}

Answer the question."""

SEMANTIC_BLOCK = """
=== DOMAIN FACTS ===
{facts}
"""

# Positive redirection, not a list of things to avoid: negative-only phrasing
# measurably fails to change model behaviour.
REDIRECTION_BLOCK = """
=== RETRIEVAL REDIRECTION (from prior failed attempts) ===
{redirections}
Address these explicitly in your answer.
"""

REDIRECTION_LINE = "- Prior attempts on this topic missed {missing}; seek and state {missing}."

# --- judge ------------------------------------------------------------------

JUDGE_SYSTEM = """You grade whether an answer is supported and complete.

Reply with EXACTLY ONE WORD and nothing else:
OK           - the answer is supported by the context and addresses the question
INSUFFICIENT - the answer is unsupported, evasive, or leaves the question open"""

JUDGE_USER = """QUESTION: {question}

ANSWER: {answer}

CONTEXT WAS:
{context}

One word:"""

# --- extract ----------------------------------------------------------------

EXTRACT_EPISODIC_SYSTEM = """You distill reusable question/answer lessons from a
completed interaction.

Reply with ONLY a JSON array. No prose, no markdown fences. At most {max_items}
objects. Each object has exactly these keys:

  "question"       - a standalone, self-contained question (string)
  "answer"         - the verified answer, one or two sentences (string)
  "evidence_type"  - one of: animal_model, observational, rct, meta_analysis, unspecified
  "confidence"     - a number between 0 and 1

Choose "evidence_type" from what the source text actually says. Use
"unspecified" when the text does not say. Return [] if nothing is worth
remembering."""

EXTRACT_EPISODIC_USER = """QUESTION ASKED:
{question}

ANSWER GIVEN:
{answer}

SOURCE CONTEXT:
{context}

JSON array:"""

EXTRACT_FAILURE_SYSTEM = """You summarise why an answer was rejected, so a future
retrieval can be redirected.

Reply with ONLY a JSON array. No prose, no markdown fences. At most {max_items}
objects. Each object has exactly these keys:

  "original_query"       - the question that failed (string)
  "bad_answer"           - a one-line summary of what was wrong (string)
  "user_feedback"        - the user's complaint, verbatim (string)
  "missing_information"  - a SHORT NOUN PHRASE naming what should have been
                           retrieved but was not, e.g. "dosage thresholds in
                           human trials". This is the important field.

Return [] if the feedback names nothing actionable."""

EXTRACT_FAILURE_USER = """QUESTION ASKED:
{question}

REJECTED ANSWER:
{answer}

USER FEEDBACK:
{feedback}

JSON array:"""

# --- classify ---------------------------------------------------------------

CLASSIFY_SYSTEM = """You compare a NEW memory against an EXISTING memory.

Reply with EXACTLY ONE WORD and nothing else:
DUPLICATE   - same claim, no new information
REFINES     - same topic, the new one adds detail or precision
CONTRADICTS - same topic, the two cannot both be true
UNRELATED   - different topics

When unsure, answer UNRELATED."""

CLASSIFY_USER = """EXISTING MEMORY:
{existing}

NEW MEMORY:
{candidate}

One word:"""

# NOTE: there is deliberately no merge prompt. REFINES merges happen in
# apply.py as a deterministic Python union, because apply.py is the only module
# that writes memory and it must contain no LLM call.
