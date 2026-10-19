"""Aggregate-only partial BIO objective and degeneration experiment.

Reads ONLY the public synthetic GT TRAIN IDs 21–35 at their pinned Git
commit. No parameter fitting, GPU, new holdout, or external model usage.
Raw source text and per-character labels stay in memory. Output never
contains résumé strings or contact details.
"""
from __future__ import annotations

import json

import httpx

from app.diagnosis.partial_bio import build_partial_bio
from app.diagnosis.partial_bio_objective import probe_degenerate_decoders
from scripts.benchmark_annotation_alignment import _disjoint_public_blob
from scripts.benchmark_partial_bio import (
    TRAIN_IDS,DEV_IDS,NEW_HOLDOUT_IDS
)
from scripts.benchmark_external_resume_corpus import IDS,COMMIT


def run() -> dict:
    assert not set(TRAIN_IDS) & (
        set(DEV_IDS)|set(NEW_HOLDOUT_IDS)|set(IDS)
    )
    records=[]
    with httpx.Client(
        timeout=20,
        headers={"User-Agent":"PaperPro-BIO-objective-test"}
    ) as client:
        for source_id in TRAIN_IDS:
            pdf=_disjoint_public_blob(
                client,f"resume_list_pdf/{source_id}.pdf"
            )
            independent=json.loads(_disjoint_public_blob(
                client,f"result_gt/{source_id}.json"
            ))
            records.append(build_partial_bio(
                pdf,independent,
                source_id=source_id,
                allowed_train_ids=TRAIN_IDS,
                forbidden_ids=tuple(DEV_IDS)+tuple(NEW_HOLDOUT_IDS)+tuple(IDS)
            ))
    diagnostics=probe_degenerate_decoders(records)
    return {
        "experiment":"partial_BIO_known_label_objective_and_degeneracy",
        "source_commit":COMMIT,
        "training_ids":list(TRAIN_IDS),
        "diagnostics":diagnostics,
        "development_pdf_read":False,
        "fresh_holdout_read":False,
        "legacy_fixed_holdout_read":False,
        "actual_model_training":False,
        "weights_saved":False,
        "production_modified":False,
        "claim_boundary":(
            "All-O and all-entity strategies can be rejected against known "
            "labels; matching known positions does not identify unknown "
            "positions or prove deployable extraction accuracy."
        ),
    }


if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=True,indent=2))
