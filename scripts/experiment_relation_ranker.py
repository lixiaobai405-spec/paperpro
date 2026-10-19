"""One-shot CPU experiment: learn company→role ranking from independent GT.

- Fit ONLY on disjoint synthetic IDs 21–40 (no held-out files).
- Evaluate once on the pre-frozen challenge IDs (1–10,101–105,201–205).
- Compare to a no-fit geometric baseline.
- No model serialization, no product integration, no API/GPU charges.
- Output aggregates only, never résumé contents or contact data.

This only tests relation ranking *given oracle-aligned endpoints*, not complete
résumé parsing accuracy, HR scoring quality, or employment truth.
"""
from __future__ import annotations

import json

from app.diagnosis.relation_ranker import (
    fit_relation_ranker, evaluate_relation_ranking
)
from scripts.benchmark_relation_pairs import collect_pairs
from scripts.benchmark_external_resume_corpus import IDS


def run() -> dict:
    train,train_stats=collect_pairs(split="train_candidate")
    model=fit_relation_ranker(train,holdout_ids=IDS)
    # The trained recipe, feature schema and scoring threshold are fixed
    # before seeing the frozen challenge labels.
    train_model=evaluate_relation_ranking(model,train)
    train_baseline=evaluate_relation_ranking(None,train)

    heldout,holdout_stats=collect_pairs(split="holdout_evaluation")
    heldout_model=evaluate_relation_ranking(model,heldout)
    heldout_baseline=evaluate_relation_ranking(None,heldout)
    if set(x["source_id"] for x in train) & set(x["source_id"] for x in heldout):
        raise RuntimeError("数据集划分违反训练/测试隔离")
    fitted_top1=heldout_model["top1_accuracy"]
    baseline_top1=heldout_baseline["top1_accuracy"]
    incremental_gain=(
        round(fitted_top1-baseline_top1,4)
        if fitted_top1 is not None and baseline_top1 is not None else None
    )
    return {
        "experiment_type":"cpu_only_linear_relation_ranker_independent_gt",
        "frozen_features":model["features"],
        "training_set":{
            **{k:v for k,v in train_stats.items()
               if k!="per_file_without_private_text"},
            "no_fit_baseline":train_baseline,
            "fitted_ranker":train_model,
        },
        "frozen_holdout":{
            **{k:v for k,v in holdout_stats.items()
               if k!="per_file_without_private_text"},
            "no_fit_baseline":heldout_baseline,
            "fitted_ranker":heldout_model,
        },
        "model_fitted":True,
        "promotion_gate":{
            "automatic_promotion_allowed":False,
            "heldout_top1_incremental_gain":incremental_gain,
            "reason":(
                "Oracle-aligned endpoint task offers no improvement over "
                "geometry-only baseline; independent end-to-end role and "
                "company candidate discovery is still missing."
            ),
        },
        "model_saved":False,
        "deployed":False,
        "external_model_or_gpu_used":False,
        "real_world_predictive_validity":False,
        "hiring_probability_claim":False,
        "quality_boundary":(
            "Only GT-unique role and employer anchors are compared. "
            "End-to-end PDF-to-schema extraction remains separately measured."
        ),
    }


if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=True,indent=2))
