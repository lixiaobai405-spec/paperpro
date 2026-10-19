"""Five independent candidate-facing diagnostic products + selected-only advice.

No hiring decision, deception accusation, or unsupported employment claims.
Computed dates and weights remain authoritative; prose can only explain them.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
import json
import re

from .schema import CandidateResume, Target
from .scoring import (
    _contains, _find, _refs, _profile, calculate_timeline, load_rules,
    score_match, weight_sensitivity, evaluate_ordinal_benchmarks, rules_prompt,
)


def _experience(resume: CandidateResume, target: Target, as_of: str) -> dict:
    result = calculate_timeline(resume, as_of=as_of)
    known = [
        (i, e) for i, e in enumerate(resume.experience)
        if e.company or e.role or e.heading
    ]
    # Employment history is often displayed newest first. Only a dated
    # chronological sequence can support a progression judgement.
    dated_indices=[int(n["path"].split(".")[1]) for n in result["timeline"]]
    titles = [(i, resume.experience[i].role) for i in dated_indices
              if resume.experience[i].role]
    level_terms = [
        ("实习", 1), ("助理", 1), ("专员", 2), ("工程师", 2), ("高级", 3),
        ("资深", 3), ("主管", 4), ("经理", 4), ("总监", 5), ("负责人", 5),
    ]
    stages = []
    for i, value in titles:
        matches = [level for term, level in level_terms if term in value]
        if matches:
            stages.append({"path":f"experience.{i}.role","original":value,"level":max(matches)})
    # Compare all observed job families, not whether a single keyword
    # appears anywhere. Unknown/ambiguous roles cannot prove continuity.
    rules=load_rules()
    families=[_profile(title,rules)[0] for _,title in titles]
    same_function=(
        len(families)>=2 and
        all(family==families[0] and family!="general" for family in families)
    )
    if len(stages)>=2 and stages[-1]["level"]>stages[0]["level"]:
        direction="可见较高职级称谓，但仍需核实职责及是否为真实晋升"
    elif len(stages)>=2 and stages[-1]["level"]<stages[0]["level"]:
        direction="职位称谓变化需要结合职责解释，不能据此推断退步"
    else:
        direction="未见明确的职级上升证据，不能仅凭职位称谓推断晋升"
    result.update({
        "career_continuity":(
            "存在相近岗位职能表述" if same_function else
            "当前记录不足以确认职业方向连贯程度"
        ),
        "career_progression": direction,
        "career_level_evidence": stages,
        "conclusion": (
            f"已登记 {len(resume.experience)} 段工作/实习经历；"
            "稳定性指标只依据明确年月计算。"
        ),
        "interpretation_boundary": "跨行业和岗位类型的变化并非缺陷；空窗与重叠可能来自求学、兼职或标注方式，须候选人确认。",
    })
    return result


def _potential(resume: CandidateResume, target: Target, as_of: str) -> dict:
    refs = _refs(resume)
    rules = load_rules()
    signals = []
    def positive_record(ref):
        return not re.search(
            r"未取得|未获得|尚未|没有|暂未|未通过|未完成|"
            r"not certified|not obtained|no credential",
            ref["original"],re.I,
        )
    work_refs=[r for r in refs if r["path"].startswith(("experience.","projects."))]
    checks = [
        ("学历", [r for r in refs if r["path"].startswith("education.") and positive_record(r)]),
        ("证书", [r for r in refs if r["path"].startswith("certificates.") and positive_record(r)]),
        # A skill list does not prove learning *speed*. Require a described
        # training, migration, promotion, or acquisition event instead.
        ("技能更新", _find(work_refs, rules["evidence_terms"]["skill_update"],positive=True)),
        ("职责扩张", _find(work_refs, rules["evidence_terms"]["responsibility_growth"],positive=True)),
        ("成果层级", _find(work_refs, rules["evidence_terms"]["metric"]+
                            rules["evidence_terms"]["leadership"],positive=True)),
    ]
    for name, support in checks:
        ref = support[0] if support else None
        signals.append({
            "signal":name,
            "status":"支持" if ref else "未体现",
            "path":ref["path"] if ref else name+"（未填写）",
            "original":ref["original"] if ref else "",
            "explanation":("仅说明简历存在对应文字证据，仍需人工确认真实性"
                           if ref else "简历未显示这一信号，不代表候选人不具备该能力"),
        })
    num=sum(item["status"]=="支持" for item in signals)
    rating="高" if num>=4 else "中" if num>=2 else "低"
    supporting=[item for item in signals if item["status"]=="支持"][:3]
    # If insufficient evidence, show the missing slots instead of fabricated facts.
    supporting += [item for item in signals if item["status"]!="支持"][:max(0,3-len(supporting))]
    needed=next((i for i in signals if i["status"]!="支持"),None)
    return {
        "status":"ok",
        "rating":rating,
        "supporting_signals":supporting,
        "signals":signals,
        "weakness":{
            "signal":needed["signal"],
            "action":"请补充该信号的可核实经历、证书或项目材料，不要推测或编造。"
        } if needed else {
            "signal":"成果的来源与可信度",
            "action":"选择最重要的两项成果，补充可核实的职责和计算口径。"
        },
        "conclusion":f"五个明确可见证据信号中有 {num} 项；该评级表示简历证据充足度，不是心理能力测验。",
        "caveat":"真实学习速度、能力潜力无法仅凭简历确定；评级不可用于人格或智力判断。",
    }


def _motivation(resume: CandidateResume, target: Target, as_of: str) -> dict:
    refs=_refs(resume)
    company_refs=_find(refs,[target.company]) if target.company.strip() else []
    role_refs=_find(refs,[target.role]) if target.role.strip() else []
    jd=target.job_description.strip()
    rules=load_rules()
    sectors=[k for k in rules["factors"][0]["keywords"] if _contains(jd,k)]
    jd_refs=_find(refs,sectors)
    count=int(bool(company_refs))+int(bool(role_refs))+int(bool(jd_refs))
    rating="高" if count>=3 else "中" if count>=1 else "低"
    evidence=(company_refs+role_refs+jd_refs)[:4]
    details=(
        "未提供目标公司，不对公司了解程度作推断，仅核对岗位表达。"
        if not target.company.strip() else
        "当前证据只来源于简历原文，不代表核验过该公司的真实需求。"
    )
    return {
        "status":"ok","rating":rating,
        "evidence":evidence,
        "rationale":f"检测到 {count} 类定制表达证据（目标公司、岗位、JD 关键词）。{details}",
        "suggestion":(
            "在自我评价或项目描述中，按真实经历指出与目标岗位匹配的技能、产出及兴趣。"
            "不要添加没有参与过的企业项目或虚构公司了解。"
        ),
        "conclusion":f"岗位针对性表述证据：{rating}。没有出现公司名称不能证明求职者不重视。",
    }


def _verification(resume: CandidateResume, target: Target, as_of: str) -> dict:
    rules=load_rules()
    timeline=calculate_timeline(resume,as_of=as_of)
    issues=list(timeline["issues"])
    dated_paths={node["path"] for node in timeline["timeline"]}
    for i,item in enumerate(resume.experience):
        path=f"experience.{i}.heading"
        if path not in dated_paths:
            reason=("工作日期有缺失，无法计算实际任期和空档。"
                    if not item.start_date or not item.end_date else
                    "起止年月格式或先后顺序异常，请核对真实任期；没有据此推测实际行为。")
            issues.append({
                "id":f"undated-{i}", "type":"工作任期需要核对",
                "location":path,
                "original":item.heading or (item.company+" "+item.role).strip() or "（没有记录）",
                "reason":reason,
                "severity":"中",
            })
    for ref in _refs(resume):
        text=ref["original"]
        # Warn only about numeric achievements with context, not years, phone or education dates.
        if ("bullets." in ref["path"] or ref["path"] in {"summary","self_evaluation"}) and re.search(
                r"\d+(?:\.\d+)?\s*(?:%|％|倍)",text):
            if not any(marker in text for marker in ("从","到","基线","对照","口径","前","后","记录","监测")):
                issues.append({
                    "id":"metric-"+ref["path"].replace(".","-"),
                    "type":"成果计算口径可追问",
                    "location":ref["path"],"original":text,
                    "reason":"成果包含量化数字，但未说明基线、测量时段或统计方式；可补充可核实的计算口径。",
                    "severity":"中",
                })
    questions=[]
    for issue in issues:
        if issue["severity"] in {"高","中"}:
            questions.append({
                "id":"question-"+issue["id"],"issue_id":issue["id"],
                "check":issue["type"],
                "question":("请结合这段经历说明具体起止时间、你的实际职责，以及可核实的证据是什么？"
                            if "时间" in issue["type"] or "任期" in issue["type"]
                            else "这项成果的计算方式、数据基线及你个人负责的部分分别是什么？"),
                "purpose":"确认简历描述的上下文与可追溯事实，不预设不诚信。",
            })
    return {
        "status":"ok","issues":issues,"questions":questions,
        "conclusion":f"检测到 {len(issues)} 项可能引起面试官追问的表述或时间问题。",
        "caveat":"自动检查无法判断真实情况；每项仅供本人核对，不构成对个人品行的评价。",
    }


def _advice(resume: CandidateResume, target: Target, dimensions: dict) -> list[dict]:
    sources=_refs(resume)
    def first(paths: list[str]):
        for p in paths:
            if p in {"experience","projects","education"}:
                found=next((x for x in sources if x["path"].startswith(p+".")),None)
            else:
                found=next((x for x in sources if x["path"]==p),None)
            if found:
                return found
        return {"path":paths[0],"original":"（该字段未填写）"}
    match=dimensions.get("match",{})
    missing_hard=[r for r in match.get("requirements",[]) if r["status"]=="简历未体现"
                  and r["id"] in {"skills","function","experience"}]
    weak_ids={r["id"] for r in missing_hard}
    templates=[
        ("岗位定位不明确","title","现有职位表述与目标岗位之间缺少直接连接。",
         "在求职方向写明实际匹配的岗位方向。",
         "求职方向：[真实具备经验的目标职位]", "高" if "function" in weak_ids else "中"),
        ("关键技能证据不足","skills","目标岗位技能的书面证据不够完整。",
         "仅补充真实掌握的技能，并在实际项目中对应到使用场景。",
         "技能：[已掌握的技术]；项目中实际使用方式：[对应任务]", "高" if "skills" in weak_ids else "中"),
        ("个人概述缺乏针对性","summary","简介未明确说明与目标岗位最相关的经历。",
         "保留真实职责，按工作领域→核心技能→可验证事项组织。",
         "曾在[真实业务领域]参与[真实职责]，主要使用[已掌握技能]。", "中"),
        ("工作职责需要更具体","experience","岗位经历中的行为边界或交付责任可能不够清晰。",
         "写明本人负责哪一步、和谁协作、交付了什么。",
         "负责[真实任务]的[本人具体部分]，交付[有证据支持的成果]。", "高" if "experience" in weak_ids else "中"),
        ("项目经历与岗位关联偏弱","projects","项目描述可能未显式证明目标岗位要求。",
         "每个项目选择一项与目标岗位直接相关的实际技能、问题和结果。",
         "项目[真实名称]：使用[真实工具]解决[真实问题]。", "中"),
        ("成果量化依据不完整","experience","成果描述如果没有统计口径，容易引出核查问题。",
         "补充能证明的基线、周期、个人职责；没有数字就写可验证的交付内容。",
         "在[已核实周期]通过[实际措施]，使[可核实指标]从[基线]变化至[结果]。", "中"),
        ("时间信息需要核对","experience","任期和空档可能尚未注明准确年月。",
         "核实每段经历真实开始/结束月份，必要时解释重叠与空档。",
         "[实际开始年月]—[实际结束年月] [实际单位]｜[真实职务]", "中"),
        ("成长证据呈现不足","certificates","证书、培训或新技能的证明材料可能未充分体现。",
         "仅列已经取得的证书、完成的培训或有交付的学习成果。",
         "证书：[真实证书名称/日期]；学习成果：[可核实项目]。", "低"),
        ("求职动机表达过于泛化","self_evaluation","简历可能没有说明为什么与目标岗位相关。",
         "结合真实经历说明岗位兴趣，企业信息只能来自用户提供的JD。",
         "希望在[目标岗位真实工作内容]中应用已有的[具体经验]。", "中"),
    ]
    advice=[]
    for i,(title,group,problem,action,example,priority) in enumerate(templates,1):
        ref=first([group,"summary"] if group != "skills" else ["skills.0","summary"])
        advice.append({
            "id":f"advice-{i:02d}","title":title,
            "priority":priority,"location":ref["path"],"original":ref["original"],
            "problem":problem,"action":action,"example":example,
            "target":(target.role or target.company),
        })
    # High-priority suggestions must be evidence-linked shortlist, not style preferences.
    return sorted(advice,key=lambda x:({"高":0,"中":1,"低":2}[x["priority"]],x["id"]))


RUNNERS={
    "match":lambda resume,target,as_of:score_match(resume,target,as_of=as_of),
    "experience":_experience,
    "potential":_potential,
    "motivation":_motivation,
    "verification":_verification,
}


def run_diagnosis(
    resume: CandidateResume, target: Target, *,
    enabled_sections: list[str] | None = None, as_of: str | None = None,
) -> dict:
    today=as_of or date.today().isoformat()
    # Validate before any partial computation.
    date.fromisoformat(today)
    rules=load_rules()
    selected=set(RUNNERS) if enabled_sections is None else set(enabled_sections)
    sections={}
    for key,runner in RUNNERS.items():
        if key not in selected:
            sections[key]={"status":"disabled","conclusion":"已按用户选择关闭该维度"}
            continue
        try:
            sections[key]=runner(resume,target,today)
        except Exception:
            # Do not leak personal input or system exceptions into report.
            sections[key]={"status":"error","conclusion":"此维度未能生成，请检查输入后重试"}
    verification=sections.get("verification",{})
    questions=verification.get("questions",[])
    # Suggestions are independent of one section's failure.
    suggestions=_advice(resume,target,sections)
    source=resume.model_dump(exclude={"source_text"})
    return {
        "meta":{
            "version":"paperpro-diagnosis-v1",
            "rules_version":rules["version"],
            "rules_status":rules["status"],
            "generated_at":datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "as_of":today,
            "source_sha256":resume.source_sha256,
            "reviewed_draft_sha256":sha256(json.dumps(source,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
            "score_is_hiring_probability":False,
            "disclaimer":"输出供候选人自查，不是实际企业录用概率；缺少真实 HR 标注数据，预测效度未验证。",
        },
        "target":target.model_dump(),
        "dimensions":sections,
        "suggestions":suggestions,
        "interview_questions":questions,
    }
