import logging
from typing import List

logger = logging.getLogger(__name__)

class EmbeddingService:
    _instance = None
    _model = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_model(self):
        if self._model is None:
            try:
                import os
                from sentence_transformers import SentenceTransformer
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                local_model_path = os.path.join(base_dir, "models", "all-MiniLM-L6-v2")
                model_name_or_path = local_model_path if os.path.exists(local_model_path) else "sentence-transformers/all-MiniLM-L6-v2"
                logger.info(f"Loading SentenceTransformer model from: {model_name_or_path}...")
                self._model = SentenceTransformer(model_name_or_path)
                logger.info("SentenceTransformer model loaded successfully.")
            except Exception as e:
                logger.error(f"Failed to load sentence-transformers model: {e}")
                self._model = None

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Compute embedding vectors for a list of text strings."""
        if not texts:
            return []
        
        self._load_model()
        if self._model is not None:
            embeddings = self._model.encode(texts, convert_to_numpy=True)
            return embeddings.tolist()
        else:
            # Fallback deterministic 384-dimensional pseudo-embedding if model is unavailable
            logger.warning("Using fallback hash-based embedding vectors.")
            results = []
            for text in texts:
                import hashlib
                h = hashlib.sha256(text.encode("utf-8")).digest()
                vector = [(float(b) / 255.0 * 2.0 - 1.0) for b in (h * 12)[:384]]
                results.append(vector)
            return results

    def embed_query(self, query: str) -> List[float]:
        """Compute embedding vector for a single query."""
        results = self.embed_texts([query])
        return results[0] if results else [0.0] * 384

embedding_service = EmbeddingService.get_instance()
