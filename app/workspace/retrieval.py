"""Offline BM25 + TF-IDF cosine, reciprocal rank fusion, lexical reranking."""

import math
import re
from collections import Counter

STOP = set(
    "a an the is are was what how when of to in on for and do does can our i me please policy".split()
)


def tokens(text):
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP]


def retrieve(documents, question, k=5, dense=None):
    corpus = [
        {**c, "document_id": d["id"], "document": d["name"], "version": d["version"]}
        for d in documents
        if d.get("active", True)
        for c in d["chunks"]
    ]
    if not corpus:
        return []
    counts = [Counter(tokens(c["text"] + " " + c["section"])) for c in corpus]
    q = Counter(tokens(question))
    n = len(corpus)
    avg = sum(sum(c.values()) for c in counts) / n or 1
    df = Counter(w for c in counts for w in c)
    idf = {w: math.log((n + 1) / (freq + 1)) + 1 for w, freq in df.items()}
    qnorm = math.sqrt(sum((v * idf.get(w, 0)) ** 2 for w, v in q.items())) or 1
    bm, tf = [], []
    for count in counts:
        length = sum(count.values())
        bm.append(
            sum(
                math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
                * count[w]
                * 2.5
                / (count[w] + 1.5 * (0.25 + 0.75 * length / avg))
                for w in q
                if count[w]
            )
        )
        norm = math.sqrt(sum((v * idf[w]) ** 2 for w, v in count.items())) or 1
        tf.append(sum(q[w] * count[w] * idf.get(w, 0) ** 2 for w in q) / (norm * qnorm))
    bmrank = {
        i: r + 1
        for r, i in enumerate(sorted(range(n), key=lambda i: bm[i], reverse=True))
        if bm[i] > 0
    }
    tfrank = {
        i: r + 1
        for r, i in enumerate(sorted(range(n), key=lambda i: tf[i], reverse=True))
        if tf[i] > 0
    }
    dense_ranks = (
        {i: r + 1 for r, i in enumerate(dense.rank(corpus, question))} if dense else {}
    )
    scored = []
    for i, c in enumerate(corpus):
        if i not in bmrank and i not in dense_ranks:
            continue
        overlap = len(set(q) & set(counts[i])) / max(1, len(q))
        rrf = (
            (1 / (60 + bmrank[i]) if i in bmrank else 0)
            + (1 / (60 + tfrank[i]) if i in tfrank else 0)
            + (1 / (60 + dense_ranks[i]) if i in dense_ranks else 0)
        )
        scored.append(
            {
                **c,
                "bm25": round(bm[i], 5),
                "tfidf": round(tf[i], 5),
                "rrf": round(rrf, 6),
                "overlap": round(overlap, 3),
                "rerank": round(rrf + overlap * 0.03, 6),
            }
        )
    return sorted(scored, key=lambda x: x["rerank"], reverse=True)[:k]


def answer(documents, question, dense=None):
    warning = None
    try:
        hits = retrieve(documents, question, dense=dense)
    except Exception:
        hits = retrieve(documents, question)
        warning = (
            "Optional dense retrieval unavailable; used offline lexical retrieval."
        )
        dense = None
    safe = [h for h in hits if not h["injection_flag"] and h["overlap"] >= 0.3]
    if not safe:
        return {
            "answer": "I cannot support an answer with the active workspace documents. Try a more specific question or upload a source.",
            "abstained": True,
            "citations": [],
            "retrieval": hits,
            "warning": warning,
            "mode": "offline extractive / BM25 + TF-IDF"
            + (" + dense Chroma" if dense else ""),
        }
    citations = safe[:3]
    result = {
        "answer": "\n\n".join(
            f"[{i + 1}] {h['text']}" for i, h in enumerate(citations)
        ),
        "abstained": False,
        "citations": citations,
        "retrieval": hits,
        "warning": warning,
        "mode": "offline extractive / BM25 + TF-IDF"
        + (" + dense Chroma" if dense else ""),
    }

    import os

    provider = os.getenv("ORCHESTRA_LLM_PROVIDER", "offline")
    if provider != "offline":
        try:
            from .llm import LLMClient

            result["optional_summary"] = LLMClient(provider).complete(
                question, result["answer"]
            )
            result["summary_notice"] = (
                "Optional provider draft; verify it against the exact cited extracts. No execution authority."
            )
        except Exception:
            result["warning"] = (
                "Optional provider unavailable. Exact offline extracts remain available."
            )
    return result
