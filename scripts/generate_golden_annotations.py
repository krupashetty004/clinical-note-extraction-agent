"""Deprecated entry point; deterministic rules cannot create clinical gold labels.

Use evaluation.generate_ai_benchmark for explicitly provisional AI annotations.
"""
from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    print(
        "This legacy annotation script is disabled. Its rule-based output could "
        "misrepresent automated labels as human-annotated or adjudicated clinical gold."
    )
    print(
        "Generate synthetic notes with scripts/prepare_100_synthetic_dataset.py, "
        "then use evaluation.generate_ai_benchmark for separately labelled AI output."
    )
    print(
        "AI-generated annotations remain provisional and are not eligible as "
        "independent clinical gold."
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
