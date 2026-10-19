"""Side-by-side, non-deployed column-reflow evaluation on pinned synthetic PDFs.

Raw PDFs and independent ground truths remain entirely in memory. No names,
emails, company names, resume sentences, or bytes printed/saved. The shipped
PDF parser is not patched or changed by this experiment.
"""
from __future__ import annotations
import json, collections, httpx, pymupdf
from app.parser import extract_file, parse_resume
from app.diagnosis.adapter import convert_resume
from app.diagnosis.pdf_layout import reordered_page_text
from scripts.benchmark_external_resume_corpus import (
    IDS,_fetch,_truth,_actual,assess,FIELDS,normalized
)


def run(ids=IDS):
    original=collections.defaultdict(lambda:[0,0])
    changed=collections.defaultdict(lambda:[0,0])
    samples=[]
    with httpx.Client(timeout=25,headers={"User-Agent":"PaperPro-layout-experiment"}) as client:
        for id_ in ids:
            source_pdf=_fetch(client,f"resume_list_pdf/{id_}.pdf")
            gt=json.loads(_fetch(client,f"result_gt/{id_}.json"))
            old_text,_,mode=extract_file(f"sample-{id_}.pdf",source_pdf)
            revised_text=old_text
            geometry=[]
            if mode=="pdf-text":
                with pymupdf.open(stream=source_pdf,filetype="pdf") as pdf:
                    if len(pdf)==1:
                        proposed,meta=reordered_page_text(pdf[0])
                        if meta["applied"]:
                            revised_text=proposed
                            geometry.append(meta)
            truth=_truth(gt)
            old=convert_resume(parse_resume(old_text),raw_text="",fingerprint="")
            new=convert_resume(parse_resume(revised_text),raw_text="",fingerprint="")
            old_record={"resume":old.model_dump()}
            new_record={"resume":new.model_dump()}
            old_hits=new_hits=0
            for k in FIELDS:
                x,n=assess(truth[k],_actual(old_record)[k])
                y,cn=assess(truth[k],_actual(new_record)[k])
                original[k][0]+=x;original[k][1]+=n
                changed[k][0]+=y;changed[k][1]+=cn
                old_hits+=x;new_hits+=y
            samples.append({
                "synthetic_id":id_,"pdf_method":mode,"reflow_applied":bool(geometry),
                "baseline_hits":old_hits,"candidate_hits":new_hits,
                "delta":new_hits-old_hits,"geometry":geometry,
                "native_ground_truth_hits_preserved":all(
                    normalized(item) in normalized(revised_text)
                    for k in FIELDS for item in truth[k]
                    if normalized(item) in normalized(old_text)
                ),
            })
    total_groundtruth=sum(a[1] for a in original.values())
    old_total=sum(a[0] for a in original.values())
    new_total=sum(a[0] for a in changed.values())
    return {
        "source":"pinned_external_synthetic_resume_corpus",
        "external_fixture_count":len(ids),
        "denominator":total_groundtruth,
        "baseline_hits":old_total,"candidate_hits":new_total,
        "net_gain":new_total-old_total,
        "baseline_rate":round(old_total/total_groundtruth,4),
        "candidate_rate":round(new_total/total_groundtruth,4),
        "category_gain":{k:changed[k][0]-original[k][0] for k in FIELDS},
        "reflow_sample_count":sum(x["reflow_applied"] for x in samples),
        "regressing_files":[{"id":s["synthetic_id"],"delta":s["delta"]}
                           for s in samples if s["delta"]<0],
        "improving_files":[{"id":s["synthetic_id"],"delta":s["delta"]}
                           for s in samples if s["delta"]>0],
        "source_field_lost_in_reordered_text":[s["synthetic_id"] for s in samples
                                            if not s["native_ground_truth_hits_preserved"]],
        "safe_per_file_metadata":samples,
        "deployed":False,"real_applicant_accuracy":False,
    }


if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=True))
