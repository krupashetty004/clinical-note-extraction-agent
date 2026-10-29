"""Run the deterministic synthetic evaluation smoke test."""

import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.metrics import evaluate_dataset
from evaluation.synthetic_smoke_dataset import build_synthetic_smoke_set


def main() -> None:
    gold_cases, predicted_cases = build_synthetic_smoke_set()
    metrics = evaluate_dataset(gold_cases, predicted_cases)

    report = {
        "evaluation_type": "synthetic_fixture_smoke_test",
        "model_evaluated": False,
        "clinical_performance_claimed": False,
        "case_count": len(gold_cases),
        "limitations": [
            "Predictions are handcrafted fixtures, not model outputs.",
            "This result does not satisfy the 100-note SOW gold-standard requirement.",
            "The fixture does not evaluate contradiction or adversarial challenge sets.",
            "The fixture does not establish clinical accuracy or deployment readiness.",
        ],
        "metrics": metrics,
    }

    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()