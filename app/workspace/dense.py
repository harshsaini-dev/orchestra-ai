"""Opt-in local sentence embeddings in tenant-isolated Chroma collections.

Requires separately installed dependencies and a locally available model path.
Never downloads a model implicitly. SQLite documents remain authoritative.
"""

import hashlib
import os
import threading
from pathlib import Path


class DenseIndex:
    def __init__(self, root, company):
        import chromadb
        from sentence_transformers import SentenceTransformer

        model_path = os.environ.get("ORCHESTRA_EMBED_MODEL_PATH", "")
        if not Path(model_path).is_dir():
            raise RuntimeError(
                "Set ORCHESTRA_EMBED_MODEL_PATH to a downloaded local sentence-transformer model directory"
            )
        self.model = SentenceTransformer(model_path, local_files_only=True)
        self.client = chromadb.PersistentClient(path=str(root))
        self.collection = self.client.get_or_create_collection(
            "tenant-" + hashlib.sha256(company.encode()).hexdigest()[:24],
            embedding_function=None,
        )
        self.lock = threading.RLock()

    def rank(self, corpus, question, k=10):
        with self.lock:
            ids = [f"{c['document_id']}:{c['version']}:{c['key']}" for c in corpus]
            old = set(self.collection.get(include=[])["ids"])
            active = set(ids)
            stale = list(old - active)
            if stale:
                self.collection.delete(ids=stale)
            missing = [i for i, key in enumerate(ids) if key not in old]
            for start in range(0, len(missing), 128):
                batch = missing[start : start + 128]
                texts = [corpus[i]["text"] for i in batch]
                vectors = self.model.encode(texts, normalize_embeddings=True).tolist()
                self.collection.upsert(
                    ids=[ids[i] for i in batch], embeddings=vectors, documents=texts
                )
            if not ids:
                return []
            vector = self.model.encode([question], normalize_embeddings=True).tolist()
            results = self.collection.query(
                query_embeddings=vector,
                n_results=min(k, len(ids)),
                include=["distances"],
            )
            lookup = {key: i for i, key in enumerate(ids)}
            return [lookup[key] for key in results["ids"][0] if key in lookup]
