"""Export synthetic source files without creating accounts in the application."""

import argparse
import csv
import json
import tempfile
from pathlib import Path
from app.workspace.store import Store
from app.workspace.demo import seed, SECTIONS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="demo_data")
    args = parser.parse_args()
    target = Path(args.out)
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        store = Store(Path(directory) / "demo.db")
        with store.tx() as s:
            seed(store, s, "export", "generator")
        for dataset in store.items("export", "dataset"):
            with (target / (dataset["category"] + ".csv")).open(
                "w", newline="", encoding="utf-8"
            ) as file:
                writer = csv.DictWriter(file, fieldnames=list(dataset["rows"][0]))
                writer.writeheader()
                writer.writerows(dataset["rows"])
        (target / "handbook.md").write_text(
            "\n\n".join("# " + title + "\n" + text for title, text in SECTIONS),
            encoding="utf-8",
        )
        (target / "manifest.json").write_text(
            json.dumps(
                {
                    "synthetic": True,
                    "seed": 42,
                    "sales_period": ["2025-01-01", "2025-12-31"],
                    "rows": 1180,
                    "planted": [
                        "duplicate sale",
                        "missing customer",
                        "whitespace",
                        "sales outlier",
                        "discount violation",
                        "low stock",
                        "large refunds",
                        "overdue invoice",
                        "leave notice breach",
                        "annual source review overdue",
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        store.engine.dispose()
    print("Synthetic source files exported to " + str(target.resolve()))


if __name__ == "__main__":
    main()
