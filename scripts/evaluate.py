"""Run the deterministic benchmark in a fresh temporary workspace."""

import json
import tempfile
from pathlib import Path
from app.workspace.store import Store
from app.workspace.demo import seed
from app.workspace.evaluation import evaluate_workspace


def main():
    with tempfile.TemporaryDirectory() as directory:
        store = Store(Path(directory) / "evaluation.db")
        with store.tx() as s:
            seed(store, s, "benchmark", "evaluator")
        print(json.dumps(evaluate_workspace(store, "benchmark"), indent=2))
        store.engine.dispose()


if __name__ == "__main__":
    main()
