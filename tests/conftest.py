import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memora_mini.store.chroma_store import ChromaMemoryStore  # noqa: E402

NS = ("memora", "test", "episodic")


@pytest.fixture
def store(tmp_path):
    return ChromaMemoryStore(path=str(tmp_path / "chroma"))
