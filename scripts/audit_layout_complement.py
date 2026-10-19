"""Audit precision/scope of conservative geometry complements on a pinned set.

Only counts and synthetic file IDs are printed. Never emit contact data,
candidate names, school names, raw text, or source document bytes.
This is not real-candidate validation and does not train any parameters.
"""
from __future__ import annotations
from collections import Counter
from hashlib import sha256
import json, httpx
from fastapi.testclient import TestClient
from app.main import app
from app.parser import extract_file,parse_resume
from app.diagnosis.adapter import convert_resume
from scripts.benchmark_external_resume_corpus import IDS,_fetch,_truth,assess


def run(ids=IDS):
    changes=Counter()
    identities=[]
    schools=[]
    violations=[]
    with httpx.Client(timeout=20,headers={"User-Agent":"PaperPro-layout-audit"}) as client:
        with TestClient(app,raise_server_exceptions=False) as api:
            for number in ids:
                blob=_fetch(client,f"resume_list_pdf/{number}.pdf")
                gt=json.loads(_fetch(client,f"result_gt/{number}.json"))
                native,_,_=extract_file("resume.pdf",blob)
                base=convert_resume(parse_resume(native),
                                    raw_text=native,fingerprint=sha256(blob).hexdigest())
                response=api.post("/api/diagnosis/parse",files={
                    "file":(f"{number}.pdf",blob,"application/pdf")
                })
                if response.status_code!=200:
                    violations.append({"id":number,"error":"file_rejected"})
                    continue
                payload=response.json()
                after=payload["resume"]
                if (after["source_sha256"] != base.source_sha256
                    or payload["source_text"]!=native
                    or after["experience"]!=[e.model_dump() for e in base.experience]
                    or after["projects"]!=[e.model_dump() for e in base.projects]
                    or after["skills"]!=base.skills):
                    violations.append({"id":number,"error":"protected_fields_modified"})
                if not base.name and after["name"]:
                    changes["filled_name"]+=1
                    correct=assess(_truth(gt)["name"],[after["name"]])[0]
                    changes["filled_name_correct"]+=correct
                    identities.append({"id":number,"matches_gt":bool(correct)})
                if not base.education and after["education"]:
                    changes["filled_education"]+=1
                    actual=[x["heading"] for x in after["education"]]
                    correct=assess(_truth(gt)["school"],actual)[0]
                    changes["filled_education_gt_entities"]+=correct
                    schools.append({"id":number,"school_gt_hit_count":correct})
    return {
        "source":"pinned_external_synthetic_pdf",
        "sample_count":len(ids),
        "counts":dict(changes),
        "name_source_precision_on_newly_filled":(
            round(changes["filled_name_correct"]/changes["filled_name"],4)
            if changes["filled_name"] else None),
        "safe_identity_metadata":identities,
        "safe_education_metadata":schools,
        "protected_field_violations":violations,
        "real_applicant_validation":False,
    }


if __name__=="__main__":
    print(json.dumps(run(),ensure_ascii=True))
