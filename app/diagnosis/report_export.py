"""F10: Render one scope-labelled, immutable-in-request diagnosis snapshot.

The current product is stateless; reports supplied by a browser are not
server-authenticated historical task versions. No claim of such verification
is made by this serializer.
"""
from __future__ import annotations

import json


SECTIONS = (
    ("match", "岗位匹配度量化"),
    ("experience", "工作经验研判"),
    ("potential", "学习能力与发展潜力"),
    ("motivation", "简历针对性"),
    ("verification", "简历疑点与风险提示"),
)
STATUSES = {"ok": "已完成", "disabled": "已关闭", "error": "失败"}


class OversizedReport(ValueError):
    """The submitted report exceeds the bounded input contract."""


def _text(value: object, max_chars: int = 600) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return ""
    return " ".join(str(value).split())[:max_chars]


def _refs(items: object, *, limit: int = 4) -> list[str]:
    if not isinstance(items, list):
        return []
    results = []
    for ref in items[:limit]:
        if not isinstance(ref, dict):
            continue
        path = _text(ref.get("path"), 120)
        value = _text(ref.get("original"), 260)
        if path or value:
            results.append(f"原文证据：{path}｜{value}")
    return results


def _match_details(section: dict) -> list[str]:
    lines = [
        f"匹配分数：{_text(section.get('score'))}/100；等级：{_text(section.get('grade'))}",
        _text(section.get("score_kind")),
        _text(section.get("calibration_warning"), 420),
    ]
    for item in (section.get("requirements") or [])[:30]:
        if not isinstance(item, dict) or item.get("status") == "岗位未要求":
            continue
        name = _text(item.get("label"), 80)
        status = _text(item.get("status"), 32)
        value = item.get("coefficient")
        weight = item.get("effective_weight")
        try:
            coefficient = f"{float(value)*100:.0f}%"
            effective_weight = f"{float(weight)*100:.1f}%"
        except (ValueError, TypeError):
            coefficient, effective_weight = "无法判断", "无法判断"
        lines.append(f"要求：{name}；状态：{status}；匹配系数：{coefficient}；有效权重：{effective_weight}")
        reason = _text(item.get("reason"), 340)
        if reason:
            lines.append("判断依据：" + reason)
        lines.extend(_refs(item.get("evidence_refs")))
    return lines


def _experience_details(section: dict) -> list[str]:
    lines = [
        "已记录任职月数（去重）：" + _text(section.get("months_total")),
        "稳定性参考分：" + _text(section.get("stability_score")),
        _text(section.get("career_continuity"), 420),
        _text(section.get("career_progression"), 420),
        _text(section.get("interpretation_boundary"), 360),
    ]
    for item in (section.get("timeline") or [])[:20]:
        if isinstance(item, dict):
            lines.append("时间节点：" + "｜".join(
                _text(item.get(field), 100) for field in ("start", "end", "company", "role", "months")
            ))
    return lines


def _potential_details(section: dict) -> list[str]:
    lines = ["证据信号评级：" + _text(section.get("rating"))]
    for item in (section.get("signals") or [])[:20]:
        if isinstance(item, dict):
            lines.append(
                "支撑信号：" + "｜".join(
                    _text(item.get(field), 300) for field in ("signal", "status", "path", "original")
                )
            )
    weakness = section.get("weakness")
    if isinstance(weakness, dict):
        lines.append("可补强项：" + _text(weakness.get("signal")))
        lines.append("补强建议：" + _text(weakness.get("action"), 360))
    return lines


def _motivation_details(section: dict) -> list[str]:
    return [
        "针对性评级：" + _text(section.get("rating")),
        "判断依据：" + _text(section.get("rationale"), 500),
        "提升建议：" + _text(section.get("suggestion"), 360),
        *_refs(section.get("evidence")),
    ]


def _verification_details(section: dict) -> list[str]:
    lines = []
    issues = section.get("issues") or []
    if not issues:
        lines.append("未发现当前规则能识别的疑点；不表示已经核实真实性。")
    for item in issues[:30]:
        if not isinstance(item, dict):
            continue
        lines.append(
            "需核对：" + _text(item.get("type"), 80)
            + "｜严重程度：" + _text(item.get("severity"), 24)
        )
        lines.append("原文位置：" + _text(item.get("location"), 180))
        lines.append("原文证据：" + _text(item.get("original"), 450))
        if item.get("related_location"):
            lines.append("对照位置：" + _text(item.get("related_location"), 180))
            lines.append("对照原文：" + _text(item.get("related_original"), 450))
        lines.append("核对原因：" + _text(item.get("reason"), 450))
    return lines


DETAILS = {
    "match": _match_details,
    "experience": _experience_details,
    "potential": _potential_details,
    "motivation": _motivation_details,
    "verification": _verification_details,
}


def render_diagnosis_report(report: dict) -> tuple[str, int]:
    """Return one version-labelled report body and count of completed modules.

    Partial successes explicitly identify missing coverage. There is no
    inference that a disabled or failed module has validated candidate facts.
    """
    if not isinstance(report, dict):
        raise ValueError("报告数据不是有效对象")
    try:
        serialized_size = len(json.dumps(report, ensure_ascii=False))
    except (ValueError, TypeError) as exc:
        raise ValueError("报告内容格式无效") from exc
    if serialized_size > 240_000:
        raise OversizedReport("诊断报告超过导出大小限制")

    meta = report.get("meta")
    target = report.get("target")
    modules = report.get("dimensions")
    if not isinstance(meta, dict) or not isinstance(target, dict) or not isinstance(modules, dict):
        raise ValueError("报告缺少输入快照或模块信息")
    for field in ("generated_at", "rules_version", "reviewed_draft_sha256", "version"):
        if not isinstance(meta.get(field), str) or not meta[field].strip() or len(meta[field]) > 160:
            raise ValueError("报告版本信息缺失")
    if not all(isinstance(modules.get(key), dict) and modules[key].get("status") in STATUSES for key, _ in SECTIONS):
        raise ValueError("报告缺少诊断模块状态")
    completed = sum(modules[key]["status"] == "ok" for key, _ in SECTIONS)
    if completed == 0:
        raise ValueError("没有有效诊断模块，不能导出报告")

    role = _text(target.get("role"), 180)
    company = _text(target.get("company"), 180)
    jd = _text(target.get("job_description"), 180)
    lines = [
        "PaperPro 五维诊断报告",
        "输出用途：候选人自查与面试准备；不代表企业录取概率或外部事实核验。",
        "报告范围：" + ("全部已完成" if completed == len(SECTIONS) else f"部分报告（{completed}/{len(SECTIONS)} 项已完成）"),
        f"生成时间：{meta['generated_at']}",
        "统计日期：" + _text(meta.get("as_of")),
        f"报告版本：{meta['version']}",
        f"规则版本：{meta['rules_version']}",
        f"简历版本指纹：{meta['reviewed_draft_sha256']}",
        "目标职位：" + (role or "未填写"),
        "目标公司：" + (company or "未填写"),
        "要求来源：" + ("用户提供的 JD" if jd else "通用岗位模型（非企业正式招聘要求）"),
        "说明：" + _text(meta.get("disclaimer"), 430),
        "",
    ]
    for key, label in SECTIONS:
        section = modules[key]
        status = STATUSES[section["status"]]
        lines.extend([f"{label}：{status}"])
        conclusion = _text(section.get("conclusion"), 460)
        if conclusion:
            lines.append("结论：" + conclusion)
        if status == "已完成":
            lines.extend(line for line in DETAILS[key](section) if line)
        else:
            lines.append("本模块未提供有效结论，不计入已完成范围。")
        lines.append("")
    return "\n".join(lines), completed
