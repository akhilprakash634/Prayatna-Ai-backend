import os
import uuid
import logging
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings
from services.embeddings import embedding_service

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CHROMA_DIR = os.path.join(BASE_DIR, "data", "chroma")
CHROMA_PATH = os.getenv("CHROMA_PATH", DEFAULT_CHROMA_DIR)
os.makedirs(CHROMA_PATH, exist_ok=True)

class RAGService:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.client = chromadb.PersistentClient(path=CHROMA_PATH)
        self.collection = self.client.get_or_create_collection(
            name="prayatna_knowledge",
            metadata={"hnsw:space": "cosine"}
        )
        logger.info(f"Initialized ChromaDB collection 'prayatna_knowledge' at {CHROMA_PATH}")

    def add_document_chunks(
        self,
        document_id: str,
        chunks: List[str],
        source_title: str,
        source_url: str,
        source_type: str
    ) -> int:
        """Embed and store chunks for a given document."""
        if not chunks:
            return 0

        embeddings = embedding_service.embed_texts(chunks)
        ids = [f"{document_id}_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "document_id": document_id,
                "title": source_title or "Prayatna Resource",
                "url": source_url or "https://prayatna.co.in/",
                "source_type": source_type,
                "chunk_index": i
            }
            for i in range(len(chunks))
        ]

        # ChromaDB batch upsert
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas
        )
        return len(chunks)

    def delete_document_chunks(self, document_id: str) -> bool:
        """Remove all chunks associated with a specific document ID."""
        try:
            self.collection.delete(where={"document_id": document_id})
            return True
        except Exception as e:
            logger.error(f"Error deleting chunks for document {document_id}: {e}")
            return False

    def query(self, query_text: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Query top-K relevant chunks with cosine similarity."""
        count = self.collection.count()
        if count == 0:
            return []

        actual_k = min(top_k, count)
        query_vector = embedding_service.embed_query(query_text)

        results = self.collection.query(
            query_embeddings=[query_vector],
            n_results=actual_k,
            include=["documents", "metadatas", "distances"]
        )

        formatted = []
        if results and results.get("documents") and len(results["documents"]) > 0:
            docs = results["documents"][0]
            metas = results["metadatas"][0] if results.get("metadatas") else []
            dists = results["distances"][0] if results.get("distances") else []

            for idx, text in enumerate(docs):
                meta = metas[idx] if idx < len(metas) else {}
                dist = dists[idx] if idx < len(dists) else 0.0
                formatted.append({
                    "content": text,
                    "metadata": meta,
                    "title": meta.get("title", "Prayatna Resource"),
                    "url": meta.get("url", "https://prayatna.co.in/"),
                    "score": round(1.0 - dist, 4) if dist is not None else 0.0
                })
        return formatted

    def get_stats(self) -> Dict[str, Any]:
        """Return total chunks and collection overview."""
        return {
            "total_chunks": self.collection.count(),
            "collection_name": self.collection.name
        }

rag_service = RAGService.get_instance()
