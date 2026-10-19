"""Offline deterministic counterfactual challenge for candidate-scoring rules.

Examples:
  uv run --python 3.12 python -m scripts.stress_test_scoring
  uv run --python 3.12 python -m scripts.stress_test_scoring --per-family 40

No real resumes, network calls, personal data, or rule weight changes.
Reported success is synthetic constraint compliance, NOT HR accuracy.
"""
from __future__ import annotations

import argparse
import json

from app.diagnosis.counterfactual_bench import evaluate_pairs

DEFAULT_SEEDS = (1021, 2026, 99)


def run_suite(
    *, seeds: tuple[int, ...] = DEFAULT_SEEDS, per_family: int = 20
) -> dict:
    if len(set(seeds)) != len(seeds) or not seeds:
        raise ValueError("Unique nonempty seeds required")
    runs = [evaluate_pairs(per_family=per_family, seed=seed) for seed in seeds]
    return {
        "validation_kind": "offline_synthetic_counterfactual_constraints",
        "rules_version": runs[0]["rules_version"],
        "seed_count": len(seeds),
        "job_families": runs[0]["role_families"],
        "total_pair_checks": sum(result["synthetic_pairs"] for result in runs),
        "total_cases_evaluated": sum(result["synthetic_cases"] for result in runs),
        "failed_checks": sum(result["failed_pairs"] for result in runs),
        "runs": [
            {"seed": seed, "pairs": result["synthetic_pairs"],
             "pass_rate": result["pairwise_pass_rate"],
             "failed": result["failed_pairs"],
             "counterexamples": result["counterexamples"]}
            for seed, result in zip(seeds, runs)
        ],
        "criterion_validated": False,
        "caveat": (
            "Synthetic invariance and monotonicity only; cannot establish "
            "real HR agreement, employee performance or hiring accuracy."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run PaperPro's synthetic counterfactual rubric benchmark."
    )
    parser.add_argument("--per-family", type=int, default=20)
    args = parser.parse_args(argv)
    try:
        output = run_suite(per_family=args.per_family)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if output["failed_checks"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
