"""Privacy-safe geometric profile of pinned, externally synthetic PDFs.

Only normalized bounding boxes, content length, section class and shape are
printed. Never emit text, names, company names or contact values.
"""
from __future__ import annotations
import httpx, pymupdf, json
from scripts.benchmark_external_resume_corpus import _fetch
from app.parser import _section

def report(ids=(1, 2, 3, 4, 5, 8, 9, 102, 105)):
    results=[]
    with httpx.Client(timeout=22,headers={"User-Agent":"PaperPro-layout-eval"}) as client:
        for id_ in ids:
            blob=_fetch(client,f"resume_list_pdf/{id_}.pdf")
            with pymupdf.open(stream=blob,filetype="pdf") as pdf:
                page_info=[]
                for p,page in enumerate(pdf):
                    blocks=[]
                    for block in page.get_text("blocks",sort=False):
                        if len(block)<7 or block[6]!=0:
                            continue
                        x0,y0,x1,y1,txt,*_=block
                        if not txt.strip():continue
                        from app.parser import _norm
                        lines=[line.strip() for line in txt.splitlines() if line.strip()]
                        candidates={_section(_norm(line)) for line in lines}
                        candidates.discard(None)
                        blocks.append({
                            "bbox":[round(x0),round(y0),round(x1),round(y1)],
                            "chars":len(txt), "lines":len(lines),
                            "section_labels":sorted(candidates)
                        })
                    page_info.append({"page":p,"size":[round(page.rect.width),round(page.rect.height)],"blocks":blocks[:36],"block_count":len(blocks)})
            results.append({"external_synthetic_id":id_,"pages":page_info})
    return results

if __name__=="__main__":
    print(json.dumps(report(),ensure_ascii=True))
