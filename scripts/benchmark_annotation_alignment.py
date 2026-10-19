"""Offline feasibility of independent-label alignment on the fixed PDF holdout.

No training, downloaded artifacts, or personal data printed. Read the same
Apache-2.0 synthetic corpus at the original pinned Git commit, in memory.
Only aggregate counts and source synthetic IDs are displayed.
"""
from __future__ import annotations

from collections import defaultdict
import argparse
import base64
import json
import os
import subprocess

import httpx

from app.diagnosis.annotation_alignment import (
    FIELD_NAMES, align_independent_annotations, prohibit_holdout_training,
    measure_work_relation_alignment
)
from scripts.benchmark_external_resume_corpus import IDS, COMMIT, ROOT, GIT_CACHE, _fetch

# A disjoint source pool for feasibility only, not a training execution.
TRAIN_POOL_IDS = tuple(range(21,41))


def _http_public_blob(client: httpx.Client, filename: str) -> bytes:
    """Read one public pinned blob directly; avoid SSH lazy-fetch stalls."""
    response=client.get(ROOT+filename,params={"ref":COMMIT})
    response.raise_for_status()
    envelope=response.json()
    if envelope.get("encoding")!="base64":
        raise ValueError("公开文件未返回预期的 base64 内容")
    content=base64.b64decode(envelope["content"])
    if len(content)>10*1024*1024:
        raise ValueError("公开样本超过单文件 10 MB 上限")
    return content


def _disjoint_public_blob(client: httpx.Client, filename: str) -> bytes:
    """Fetch a pinned public Git object without SSH rewrites or API quota.

    Use the existing OS-temp blobless clone, never the product repository.
    This host's global Git config rewrites GitHub HTTPS to SSH. A second
    "url.insteadOf" config value does *not* remove the original multi-value.
    Disable global Git config for this child process only, leaving user's
    global settings untouched. The clone's pinned origin remains HTTPS.
    Missing blobs are cached in the external Git clone, not PaperPro.
    """
    if not (GIT_CACHE / ".git").is_dir():
        return _http_public_blob(client, filename)

    head=subprocess.run(
        ["git","-C",str(GIT_CACHE),"rev-parse","HEAD"],
        capture_output=True,text=True,timeout=10,check=False,
    )
    if head.returncode!=0 or head.stdout.strip()!=COMMIT:
        raise ValueError("外部 Git 缓存不符合固定 commit")

    cmd=["git","-C",str(GIT_CACHE),"show",f"{COMMIT}:{filename}"]
    environment={
        **os.environ,
        "GIT_CONFIG_GLOBAL":os.devnull,
        "GIT_TERMINAL_PROMPT":"0",
    }
    blob_process=subprocess.run(
        cmd,capture_output=True,timeout=55,check=False,env=environment
    )
    if blob_process.returncode!=0:
        raise ValueError("无法从固定 Git 仓库读取外部样本 Blob")
    blob=blob_process.stdout
    if not blob or len(blob)>10*1024*1024:
        raise ValueError("外部样本为空或超过 10 MB")
    return blob


def run(ids=IDS, *, split: str = "holdout_evaluation") -> dict:
    if split == "holdout_evaluation":
        if tuple(ids) != IDS:
            raise ValueError("固定外部保留集不允许替换编号或分母")
    elif split == "train_candidate_feasibility":
        for source_id in ids:
            prohibit_holdout_training(source_id,holdout_ids=IDS)
    else:
        raise ValueError("未知的数据集划分")
    counts=defaultdict(lambda:{
        "expected":0,"unique_native_line":0,
        "ambiguous_multiple_lines":0,"not_found_in_native_lines":0
    })
    records=[]
    relation_totals=defaultdict(int)
    with httpx.Client(
        timeout=24,headers={"User-Agent":"PaperPro-annotation-feasibility"}
    ) as client:
        get_blob=(
            _fetch if split=="holdout_evaluation" else _disjoint_public_blob
        )
        for source_id in ids:
            # The fixed set stays on the cached, pinned Git object transport.
            # Disjoint feasibility cases use HTTP, never lazy SSH blob fetch.
            pdf_bytes=get_blob(client,f"resume_list_pdf/{source_id}.pdf")
            gt=json.loads(get_blob(client,f"result_gt/{source_id}.json"))
            aligned=align_independent_annotations(pdf_bytes,gt)
            relation=measure_work_relation_alignment(aligned,gt)
            for key,value in relation.items():
                relation_totals[key]+=value
            per_file={}
            for field in FIELD_NAMES:
                rec=aligned["field_counts"][field]
                per_file[field]={
                    "expected":rec["expected"],
                    "unique_native_line":rec["unique_native_line"]
                }
                for key in counts[field]:
                    counts[field][key]+=rec[key]
            records.append({
                "synthetic_id":source_id,
                "native_lines":aligned["native_line_count"],
                "unique_anchor_count":len(aligned["unique_anchors"]),
                "per_field":per_file,
            })
    summary={
        name:{**count,"single_line_alignment_rate":(
            round(count["unique_native_line"]/count["expected"],4)
            if count["expected"] else None
        )}
        for name,count in counts.items()
    }
    return {
        "source":"external_synthetic_pdf_independent_gt",
        "split":split,
        "commit":COMMIT,
        "source_ids":list(ids),
        "count":len(ids),
        "field_counts":{name:summary.get(name,{
            "expected":0,"unique_native_line":0,
            "ambiguous_multiple_lines":0,"not_found_in_native_lines":0,
            "single_line_alignment_rate":None
        }) for name in FIELD_NAMES},
        "per_file_without_private_text":records,
        "work_relation_feasibility":dict(relation_totals),
        "training_examples_emitted":0,
        "field_annotation_sources":"dataset_gt_not_PaperPro_scores",
        "independent_training_dataset_required":True,
        "real_applicant_validation":False,
        "caveat":"Textual alignment alone is not a verified job-role pairing or trained model.",
    }


if __name__=="__main__":
    parser=argparse.ArgumentParser(
        description="Measure GT→PDF text-line alignment without training any model."
    )
    parser.add_argument("--split",default="holdout_evaluation",
                        choices=["holdout_evaluation","train_candidate_feasibility"])
    args=parser.parse_args()
    ids = IDS if args.split=="holdout_evaluation" else TRAIN_POOL_IDS
    measured=run(ids,split=args.split)
    print(json.dumps({key:value for key,value in measured.items()
                      if key!="per_file_without_private_text"},ensure_ascii=True,indent=2))
