import logging
import os
import re
import shutil
import threading
from typing import Any, Dict, List, Optional

import chromadb

from services.embeddings import embedding_service

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CHROMA_DIR = os.path.join(BASE_DIR, "data", "chroma")
CHROMA_PATH = os.getenv("CHROMA_PATH", DEFAULT_CHROMA_DIR)
os.makedirs(CHROMA_PATH, exist_ok=True)

SLUG_REGEX = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
COLLECTION_REGEX = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{1,100}$")


def sanitize_org_slug(org_slug: str) -> str:
    val = (org_slug or "").strip().lower()
    if not val or not SLUG_REGEX.match(val):
        raise ValueError(f"Invalid organization slug for RAG isolation: {org_slug!r}")
    return val


def sanitize_collection_name(collection_name: Optional[str], org_slug: str) -> str:
    if collection_name and COLLECTION_REGEX.match(collection_name):
        return collection_name
    return f"org_{org_slug.replace('-', '_')}"


class RAGService:
    _instance = None
    _init_lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._base_path = os.path.realpath(os.getenv("CHROMA_PATH", CHROMA_PATH))
        os.makedirs(self._base_path, exist_ok=True)
        self._clients: Dict[str, chromadb.PersistentClient] = {}
        self._lock = threading.Lock()

    def set_base_path(self, path: str) -> None:
        """Reconfigure Chroma root directory cleanly (useful for automated tests)."""
        with self._lock:
            self._clients.clear()
            self._base_path = os.path.realpath(path)
            os.makedirs(self._base_path, exist_ok=True)

    def _get_org_dir(self, org_slug: str) -> str:
        safe_slug = sanitize_org_slug(org_slug)
        target_dir = os.path.realpath(os.path.join(self._base_path, safe_slug))
        if not target_dir.startswith(self._base_path + os.sep):
            raise ValueError("Invalid organization vector directory path")
        os.makedirs(target_dir, exist_ok=True)
        return target_dir

    def _get_client(self, org_slug: str) -> chromadb.PersistentClient:
        safe_slug = sanitize_org_slug(org_slug)
        with self._lock:
            client = self._clients.get(safe_slug)
            if client is None:
                org_dir = self._get_org_dir(safe_slug)
                client = chromadb.PersistentClient(path=org_dir)
                self._clients[safe_slug] = client
            return client

    def get_collection(self, org_slug: str = "prayatna", collection_name: Optional[str] = None):
        safe_slug = sanitize_org_slug(org_slug)
        safe_coll = sanitize_collection_name(collection_name, safe_slug)
        client = self._get_client(safe_slug)
        return client.get_or_create_collection(
            name=safe_coll,
            metadata={"hnsw:space": "cosine"},
        )

    def ensure_org_collection(self, org_slug: str, collection_name: Optional[str] = None) -> str:
        coll = self.get_collection(org_slug=org_slug, collection_name=collection_name)
        return coll.name

    def add_document_chunks(
        self,
        document_id: str,
        chunks: List[str],
        source_title: str,
        source_url: str,
        source_type: str,
        org_slug: str = "prayatna",
        collection_name: Optional[str] = None,
    ) -> int:
        """Embed and store chunks strictly inside the specified organization's Chroma collection."""
        if not chunks:
            return 0

        collection = self.get_collection(org_slug=org_slug, collection_name=collection_name)
        embeddings = embedding_service.embed_texts(chunks)
        ids = [f"{document_id}_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "document_id": document_id,
                "organization_slug": sanitize_org_slug(org_slug),
                "title": source_title or "Knowledge Resource",
                "url": source_url or "",
                "source_type": source_type,
                "chunk_index": i,
            }
            for i in range(len(chunks))
        ]

        collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas,
        )
        return len(chunks)

    def delete_document_chunks(
        self,
        document_id: str,
        org_slug: str = "prayatna",
        collection_name: Optional[str] = None,
    ) -> bool:
        """Remove all chunks associated with a specific document ID within an organization."""
        try:
            collection = self.get_collection(org_slug=org_slug, collection_name=collection_name)
            collection.delete(where={"document_id": document_id})
            return True
        except Exception as e:
            logger.error("Error deleting chunks for document %s in org %s: %s", document_id, org_slug, e)
            return False

    def query(
        self,
        query_text: str,
        top_k: int = 5,
        org_slug: str = "prayatna",
        collection_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Query top-K relevant chunks strictly inside the specified organization's collection."""
        collection = self.get_collection(org_slug=org_slug, collection_name=collection_name)
        count = collection.count()
        if count == 0:
            return []

        actual_k = min(top_k, count)
        query_vector = embedding_service.embed_query(query_text)

        results = collection.query(
            query_embeddings=[query_vector],
            n_results=actual_k,
            include=["documents", "metadatas", "distances"],
        )

        formatted: List[Dict[str, Any]] = []
        if results and results.get("documents") and len(results["documents"]) > 0:
            docs = results["documents"][0]
            metas = results["metadatas"][0] if results.get("metadatas") else []
            dists = results["distances"][0] if results.get("distances") else []

            for idx, text in enumerate(docs):
                meta = metas[idx] if idx < len(metas) else {}
                dist = dists[idx] if idx < len(dists) else 0.0
                formatted.append(
                    {
                        "content": text,
                        "metadata": meta,
                        "title": meta.get("title", "Knowledge Resource"),
                        "url": meta.get("url", ""),
                        "score": round(1.0 - dist, 4) if dist is not None else 0.0,
                    }
                )
        return formatted

    def get_stats(self, org_slug: str = "prayatna", collection_name: Optional[str] = None) -> Dict[str, Any]:
        """Return total chunks and collection overview for a specific organization."""
        collection = self.get_collection(org_slug=org_slug, collection_name=collection_name)
        return {
            "total_chunks": collection.count(),
            "collection_name": collection.name,
            "org_slug": sanitize_org_slug(org_slug),
        }

    def delete_org_store(self, org_slug: str) -> None:
        """Delete an organization's isolated Chroma directory and cached client."""
        safe_slug = sanitize_org_slug(org_slug)
        with self._lock:
            self._clients.pop(safe_slug, None)
        target_dir = os.path.realpath(os.path.join(self._base_path, safe_slug))
        if target_dir.startswith(self._base_path + os.sep) and os.path.exists(target_dir):
            shutil.rmtree(target_dir, ignore_errors=True)

    def migrate_legacy_collection(
        self,
        legacy_collection_name: str = "prayatna_knowledge",
        target_org_slug: str = "prayatna",
        target_collection_name: str = "org_prayatna",
    ) -> int:
        """
        Idempotently copy vectors from the legacy single-tenant root Chroma collection
        (`prayatna_knowledge`) into Prayatna's isolated org collection (`data/chroma/prayatna`).
        """
        legacy_sqlite = os.path.join(self._base_path, "chroma.sqlite3")
        if not os.path.exists(legacy_sqlite):
            return 0

        target_collection = self.get_collection(
            org_slug=target_org_slug,
            collection_name=target_collection_name,
        )
        if target_collection.count() > 0:
            return target_collection.count()

        try:
            legacy_client = chromadb.PersistentClient(path=self._base_path)
            existing_names = [c.name for c in legacy_client.list_collections()]
            if legacy_collection_name not in existing_names:
                return 0

            legacy_coll = legacy_client.get_collection(name=legacy_collection_name)
            total = legacy_coll.count()
            if total == 0:
                return 0

            batch = legacy_coll.get(include=["documents", "embeddings", "metadatas"])
            ids = batch.get("ids") or []
            docs = batch.get("documents") or []
            embeddings = batch.get("embeddings")
            metadatas = batch.get("metadatas") or [{} for _ in ids]

            if not ids:
                return 0

            safe_metas = []
            for m in metadatas:
                item = dict(m or {})
                item["organization_slug"] = target_org_slug
                safe_metas.append(item)

            if embeddings is not None and len(embeddings) == len(ids):
                # Convert numpy arrays if returned as ndarray
                emb_list = [e.tolist() if hasattr(e, "tolist") else list(e) for e in embeddings]
                target_collection.upsert(
                    ids=ids,
                    embeddings=emb_list,
                    documents=docs,
                    metadatas=safe_metas,
                )
            else:
                emb_list = embedding_service.embed_texts(docs)
                target_collection.upsert(
                    ids=ids,
                    embeddings=emb_list,
                    documents=docs,
                    metadatas=safe_metas,
                )

            logger.info(
                "Migrated %d legacy vectors from '%s' to isolated org '%s' (%s).",
                len(ids),
                legacy_collection_name,
                target_org_slug,
                target_collection_name,
            )
            return len(ids)
        except Exception as e:
            logger.error("Failed migrating legacy Chroma collection '%s': %s", legacy_collection_name, e)
            return 0


rag_service = RAGService.get_instance()
