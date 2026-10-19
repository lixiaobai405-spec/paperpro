# PaperPro：部分标注 BIO 目标函数与退化解实验（2026-10-19）

**状态：完成数学目标与反例验证；没有训练或部署模型，也没有读取冻结测试集。**

## 数据与边界

来源：公开 Apache-2.0 合成 PDF 数据集 SyntheticResumeData，固定 commit 为 3ecd09129f65955e743aacf67f2785fcee10d461。本轮只使用训练编号 21–35（15 份），未访问开发集 36–40、全新冻结测试集 41–60、历史固定挑战集 1–10/101–105/201–205。

训练集总共 601 条原生文字行、9,706 个字符：477 个独立 GT 的正向工作职位/公司/学校字符、346 个独立 GT 唯一定位且不重叠的电话/邮箱背景 O 字符、8,883 个仍是 UNKNOWN 的字符（91.52%）。联系方式 O 只意味着“不属于三个目标字段”，并不代表“不是任何实体”。

## 实现和精确性

源码：app/diagnosis/partial_bio_objective.py。七个状态为 O、B/I-WORK_ROLE、B/I-EMPLOYER、B/I-SCHOOL。对任一 PDF 文字行，设 Y 是所有 BIO 转移合法序列的集合，Y_obs 是另外满足已观察 GT 标签的序列。以发射分数 S(y) 定义：

    L_partial = logsumexp_{y in Y} S(y) - logsumexp_{y in Y_obs} S(y)

UNKNOWN 位置以合法序列枚举的 logsumexp 边际化，不擅自设置 O；无标签的整行损失为 0。使用稳定前向动态规划计算，而不是枚举指数级路径；还实现仅在有 GT 标签字符上计算的 masked-token 交叉熵作为对照。

测试将四个字符的 BIO 所有合法路径穷举，确认与动态规划结果一致，拒绝非法 I- 转移、NaN/Inf、无合法路径和标签/掩码不匹配。这不等于训练了带参数转移的 CRF，也不证明能抽取未见 PDF 字段。

## 15 份训练 PDF 的退化策略对照

命令：

    uv run --python 3.12 python -m scripts.benchmark_partial_bio_objective
    uv run --python 3.12 python -m pytest tests/test_partial_bio_objective.py -q

给每个策略预定标签 logit +7，其他标签 -7；没有模型拟合、GPU、外部收费服务。

| 策略 | 823 个已知字符上的错误数 | 已知位置平均 CE | 合计部分 BIO NLL |
|---|---:|---:|---:|
| 全 O | 477 | 8.114221 | 6678.002042 |
| 全 B-WORK_ROLE | 799 | 13.591743 | 11186.002688 |
| 记住已标注位置，其余均预测 O | 0 | 约 0.000005 | 0.001363 |
| 记住已标注位置，其余均预测 B-WORK_ROLE | 0 | 约 0.000005 | 0.001373 |

两个记忆策略在全部 8,883 个 UNKNOWN 字符上给出相反预测，却都得到近乎零的目标函数损失。这是**训练损失不足以判断未知位置正确性**的可运行反例。已知 GT 能拒绝全 O/全实体的粗糙退化，但不足以约束未标注大部分字符。

两种记忆策略都标为不具备部署资格；冻结测试和训练许可保持关闭。合计 NLL 受字数、已观测数量和人为 ±7 幅度影响，不能用于其他模型质量排名。这是训练前结构可辨识性测试，不是自动抽取准确率。

## 工程门禁与后续

明确保留 promotion_gate.pass=false，training_or_deployment_authorized=false，frozen_holdout_access_allowed=false。下一阶段应先增加独立、可溯源、经过字段冲突校验的非目标区间（例如已核实的日期或姓名）作为额外部分监督，或证明合法的部分标签序列目标能够控制未知区域的退化预测。切不可把整行未标注字符擅自变成背景 O；如果未来训练 CPU 原型，须对完整片段边界及端到端 PDF→Schema 质量设独立门槛。

正式 PaperPro 页面、settings.json、五维匹配评分和原文件 SHA 校验均未被本实验修改。旧的外部 20 PDF、276 GT 项基准仍为 167/276（60.51%），没有声称新功能通过 R7-1 的真实精度验收。

## 相关代码

- app/diagnosis/partial_bio.py：B/I/O 与 UNKNOWN、来源合法性。
- app/diagnosis/partial_bio_objective.py：精确部分 CRF 损失、masked CE、退化策略诊断。
- scripts/benchmark_partial_bio_objective.py：仅从训练集产生安全聚合。
- tests/test_partial_bio_objective.py：数值一致性、BIO 反例、退化识别及推广门禁。
