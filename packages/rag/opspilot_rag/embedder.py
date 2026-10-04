import hashlib
import random
from typing import List, Protocol

class Embedder(Protocol):
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        ...
        
    def embed_query(self, text: str) -> List[float]:
        ...

class MockEmbedder:
    """A deterministic mock embedder for no-cost local testing."""
    def __init__(self, dimension: int = 384):
        self.dimension = dimension

    def _generate_mock_vector(self, text: str) -> List[float]:
        # Create a deterministic but pseudo-random vector based on the text hash
        hash_val = int(hashlib.md5(text.encode("utf-8")).hexdigest(), 16)
        random.seed(hash_val)
        return [random.uniform(-1, 1) for _ in range(self.dimension)]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._generate_mock_vector(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._generate_mock_vector(text)
