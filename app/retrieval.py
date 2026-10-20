"""Transparent lexical policy retrieval; no embedding downloads are needed."""
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path


def tokens(text):
    return re.findall(r"[a-z0-9]+", text.lower())


class PolicyIndex:
    def __init__(self, path: Path):
        self.path = path

    def load(self):
        raw = self.path.read_bytes()
        return json.loads(raw), hashlib.sha256(raw).hexdigest()

    def search(self, query, intent="unknown", limit=3):
        policies, digest = self.load()
        docs = [tokens(p["title"] + " " + p["text"]) for p in policies]
        average = sum(map(len, docs)) / len(docs)
        query_tokens = set(tokens(query + " " + intent))
        scores = []
        for p, words in zip(policies, docs):
            counts = Counter(words)
            score = 0.0
            for term in query_tokens:
                df = sum(term in d for d in docs)
                idf = math.log(1 + (len(docs) - df + .5) / (df + .5))
                tf = counts[term]
                score += idf * tf * 2.5 / (tf + 1.5 * (.25 + .75 * len(words) / average))
            # Intent routing ensures the governing policy is always retrieved.
            if intent in p["intents"] and p["id"] != "POL-CONTROL":
                score += 10
            scores.append({**p, "score": round(score, 4), "source": "data/policies.json"})
        scores.sort(key=lambda p: (-p["score"], p["id"]))
        selected = scores[:limit]
        # Control evidence is mandatory even when a long query ranks other docs higher.
        control = next(p for p in scores if p["id"] == "POL-CONTROL")
        if limit >= 2 and control not in selected:
            selected[-1] = control
        return selected, digest
