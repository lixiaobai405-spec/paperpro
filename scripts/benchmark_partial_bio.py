"""TRAIN-ONLY aggregate benchmark for partially observed PDF BIO labels.

Reads exactly the cached public synthetic PDF+independent GT of IDs 21–35
from the pinned commit, without touching development (36–40), new holdout
(41–60), or the older frozen challenge. No external model/API charges.

Raw résumé text, GT field values, char labels, and byte content remain only
in RAM; the CLI prints *aggregates* and never persists any documents.
"""
from __future__ import annotations

import json
import httpx

from app.diagnosis.partial_bio import build_partial_bio, summarize_partial_bio
from scripts.benchmark_annotation_alignment import _disjoint_public_blob
from scripts.benchmark_external_resume_corpus import COMMIT, IDS

TRAIN_IDS=tuple(range(21,36))
DEV_IDS=tuple(range(36,41))
NEW_HOLDOUT_IDS=tuple(range(41,61))
assert set(TRAIN_IDS).isdisjoint(set(DEV_IDS)|set(NEW_HOLDOUT_IDS)|set(IDS))


def run() -> dict:
    records=[]
    forbidden=tuple(DEV_IDS)+tuple(NEW_HOLDOUT_IDS)+tuple(IDS)
    with httpx.Client(
        timeout=20, headers={"User-Agent":"PaperPro-partial-BIO-feasibility"}
    ) as http:
        for source_id in TRAIN_IDS:
            pdf=_disjoint_public_blob(
                http,f"resume_list_pdf/{source_id}.pdf"
            )
            independent_gt=json.loads(_disjoint_public_blob(
                http,f"result_gt/{source_id}.json"
            ))
            records.append(build_partial_bio(
                pdf,independent_gt,
                source_id=source_id,
                allowed_train_ids=TRAIN_IDS,
                forbidden_ids=forbidden,
            ))
    aggregate=summarize_partial_bio(records)
    return {
        "experiment":"independent_GT_partially_observed_BIO_data_interface",
        "source_commit":COMMIT,
        "source_kind":"public_synthetic_training_pool_only",
        "source_count":len(TRAIN_IDS),
        "sources_used":list(TRAIN_IDS),
        "statistics":aggregate,
        "development_pool_read":False,
        "fresh_holdout_read":False,
        "legacy_fixed_holdout_read":False,
        "actual_training_performed":False,
        "background_labels_verified":aggregate["observed_O_count"]>0,
        "background_scope":"only unique, format-checked, non-overlapping independent-GT contacts",
        "complete_background_annotation":False,
        "deployment_allowed":False,
        "actual_pdf_to_schema_benchmark_unchanged":True,
    }


if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=True,indent=2))
