"""Conservative two-column text ordering experiment.

This module does not infer resume fields, identity, or dates. It only groups
native PyMuPDF text blocks geometrically when the page has a convincing pair
of spatially separated independent columns. Non-column pages are untouched.

All blocks and characters are kept; only their reading order changes.
"""
from __future__ import annotations
import pymupdf


def _pdf_text_blocks(page: pymupdf.Page) -> list[dict]:
    result=[]
    for block in page.get_text("blocks",sort=False):
        if len(block)<7 or block[6]!=0:
            continue
        x0,y0,x1,y1,text,*_=block
        if not text.strip():
            continue
        result.append({
            "x0":float(x0),"x1":float(x1),
            "y0":float(y0),"y1":float(y1),
            "text":text.strip(),
            "chars":len(text.strip()),
        })
    return result


def detect_columns(page: pymupdf.Page) -> tuple[float, int, int, int] | None:
    blocks=_pdf_text_blocks(page)
    # Large one-page drawings may contain thousands of independently placed
    # text objects; avoid quadratic layout heuristics on such input.
    if not 10<=len(blocks)<=180:
        return None
    width=page.rect.width
    best=None
    # A genuine split has a substantial number of blocks entirely on either
    # side and very few bridges. Embedded sidebar labels are allowed only if
    # there is enough independent text to form a real column.
    for fraction in range(18,82,2):
        boundary=width*fraction/100
        left=[b for b in blocks if b["x1"] <= boundary-5]
        right=[b for b in blocks if b["x0"] >= boundary+5]
        bridge=[b for b in blocks if b not in left and b not in right]
        if min(len(left),len(right))<4:
            continue
        total_chars=sum(b["chars"] for b in blocks)
        lchars=sum(b["chars"] for b in left)
        rchars=sum(b["chars"] for b in right)
        if min(lchars,rchars)<max(80,total_chars*.10):
            continue
        if len(bridge)>len(blocks)*.23:
            continue
        # There must be simultaneous text in left and right regions.
        lrange=(min(b["y0"] for b in left),max(b["y1"] for b in left))
        rrange=(min(b["y0"] for b in right),max(b["y1"] for b in right))
        overlap=max(0,min(lrange[1],rrange[1])-max(lrange[0],rrange[0]))
        if overlap<min(lrange[1]-lrange[0],rrange[1]-rrange[0])*.45:
            continue
        score=(len(left)+len(right))-(len(bridge)*2)
        score+=min(lchars,rchars)/max(lchars,rchars)
        if best is None or score>best[0]:
            best=(score,boundary,len(left),len(right),len(bridge))
    if not best:
        return None
    return best[1:]


def reordered_page_text(page: pymupdf.Page) -> tuple[str,dict]:
    blocks=_pdf_text_blocks(page)
    split=detect_columns(page)
    if not split:
        return page.get_text("text",sort=True).strip(),{"applied":False}
    boundary,left_count,right_count,bridge_count=split
    left=[b for b in blocks if b["x1"]<=boundary-5]
    right=[b for b in blocks if b["x0"]>=boundary+5]
    other=[b for b in blocks if b not in left and b not in right]
    # Cross-column blocks can be full-width headings. Prepend top headings;
    # remaining bridges are appended so none are discarded.
    top=min(b["y0"] for b in (left+right))
    headings=[b for b in other if b["y1"]<top]
    rest=[b for b in other if b not in headings]
    by_y=lambda b:(b["y0"],b["x0"])
    ordered=sorted(headings,key=by_y)+sorted(left,key=by_y)+sorted(right,key=by_y)+sorted(rest,key=by_y)
    return "\n".join(b["text"] for b in ordered),{
        "applied":True,"boundary_fraction":round(boundary/page.rect.width,3),
        "left_blocks":left_count,"right_blocks":right_count,"bridge_blocks":bridge_count,
        "text_block_count":len(blocks),
    }


def _source_contains(original_text: str, item: str) -> bool:
    """Field must literally occur in the already-extracted PDF text."""
    import re
    strip=lambda s:re.sub(r"[\s|丨｜·•]+","",s).casefold()
    return bool(item.strip()) and strip(item) in strip(original_text)


def conservative_complement(
    current, alternative, *, original_text: str,
) -> tuple[object,list[str]]:
    """Return a *copy* with a verified missing name/school, never job details.

    The layout hypothesis may reorder sections and is not entitled to change
    an existing identity, employment period, work role, project or document
    hash. The review UI must still ask the user to verify these new fields.
    """
    import re
    result=current.model_copy(deep=True)
    changes=[]
    name=(alternative.name or "").strip()
    if (not result.name and
        re.fullmatch(r"[\u4e00-\u9fff]{2,6}",name) and
        not re.search(r"工作|实习|经历|教育|简介|项目|技能|简历|"
                      r"公司|企业|学院|大学|学校|联系方式|联系人|姓名|名字|个人信息|"
                      r"经理|工程师|招聘|岗位|职位|候选人",name) and
        _source_contains(original_text,name)):
        result.name=name
        changes.append("name")
    if not result.education:
        possible=[]
        seen=set()
        for item in alternative.education:
            head=item.heading.strip()
            if not (5<=len(head)<=155 and
                    re.search(r"大学|学院|学校|university|college",head,re.I)
                    and _source_contains(original_text,head)
                    and not re.search(r"@|电话|手机|\b1[3-9]\d{9}\b",head)):
                continue
            if head.casefold() in seen:
                continue
            seen.add(head.casefold())
            possible.append(item)
        if len(possible)==1:
            result.education=[possible[0].model_copy(deep=True)]
            changes.append("education")
    return result,changes


def augment_missing_fields_from_pdf(
    candidate, content: bytes, *, method: str,
) -> tuple[object,list[str]]:
    """Opt-in candidate-only complement, read-only on PDF bytes/source text.

    The classic editor uses its previous parsing pipeline unchanged.
    """
    if method!="pdf-text" or (candidate.name and candidate.education):
        return candidate,[]
    from app.parser import parse_resume
    with pymupdf.open(stream=content,filetype="pdf") as pdf:
        if len(pdf)!=1:
            return candidate,[]
        proposal,meta=reordered_page_text(pdf[0])
    if not meta.get("applied"):
        return candidate,[]
    other=parse_resume(proposal)
    return conservative_complement(
        candidate,other,original_text=candidate.source_text
    )
