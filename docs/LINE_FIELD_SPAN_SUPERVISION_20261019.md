# PaperPro｜PDF 行分类与字符区间监督实验（2026-10-19）

结论：**整行分类模型未通过开发验证，未部署；字符区间标注恢复了被错误丢弃的正向监督信号。**

## 数据与验收边界

外部数据：Apache-2.0 开源 SyntheticResumeData，固定 Git commit 3ecd09129f65955e743aacf67f2785fcee10d461。原始训练编号 21–35（15 份）、扩展训练 61–80（新增 20 份），独立开发验证 36–40（5 份）。全新冻结测试集 41–60 **本轮未读取**。既有完整解析挑战集 1–10、101–105、201–205 绝不训练或用于调整参数，其产品基线仍为 167/276（60.51%）。

## 整行分类模型

- 源码：app/diagnosis/line_field_classifier.py，scripts/experiment_line_field_classifier.py。
- 监督标签只来自外部 GT 唯一文字行的职位、公司、学校正向标注，未标注行不能视为负例。
- GT-blind 推理只接受 PDF 和模型，用 768 维字符 n-gram 哈希 + 13 项几何/文本结构特征；固定 CPU NumPy softmax，420 轮、学习率 0.38、L2=0.018。
- 相同字段最多给 8 个待核对行。排序得分**不是**经过校准的职位真实性概率，也不是 HR 匹配分。
- 与旧的无训练词表规则在同样 5 份验证 PDF、同样每字段复核额度下比较。

| 开发验证指标 | 旧规则 | 训练 15 PDF | 扩展训练 35 PDF |
|---|---:|---:|---:|
| 独立职位正向锚点（训练池） | - | 14 | 39 |
| 独立公司正向锚点（训练池） | - | 18 | 58 |
| 独立学校正向锚点（训练池） | - | 10 | 34 |
| 职位文字行 GT 覆盖 | **10/13** | 5/13 | 5/13 |
| 公司文字行 GT 覆盖 | **10/14** | 7/14 | 9/14 |
| 待人工核对的候选行数 | **33** | 80 | 80 |

开发门禁提前固定：职位与公司覆盖均不能低于基线，且人工候选行不能超过旧规则完整清单的 1.5 倍。两种训练规模均失败，故**不执行全新冻结测试、不自动部署、不继续在小验证集上反复调词表或超参数**。

扩展训练时本机 GitHub 智能 Git 端点暂不可达，新增 61–80 号公开 PDF 通过固定 commit 的 GitHub Contents API 在内存下载；其余已缓存的文件仍使用临时 Git 克隆。没有改变全局 Git 配置或保存外部个人资料。

运行命令：

    uv run --python 3.12 python -m scripts.experiment_line_field_classifier --split development_validation --training small
    uv run --python 3.12 python -m scripts.experiment_line_field_classifier --split development_validation --training expanded

失败时 --split new_unseen_test 直接返回 fresh_test_read=false，不读取编号 41–60。

## 找到的上游监督结构问题

公司与职位可能是**同一 PDF 文字行内互不重叠的两个字符片段**。旧整行互斥分类接口把这种行当成冲突，丢失重要标签。因此新增 app/diagnosis/span_supervision.py，以原始字符区间 start_char/end_char 与独立 GT 对齐，允许一行携带多个不同字段标签。重复文本、重叠区间、找不到文字都弃权；没有为未标注文本生成负例，也没有声称任职关系已经核实。

只用缓存的 15 份训练 PDF（21–35）验证：

| 正向监督锚点 | 旧整行分类 | 新字符区间 | 增量 |
|---|---:|---:|---:|
| 职位 | 14 | **24** | **+10** |
| 公司 | 18 | **28** | **+10** |
| 学校 | 10 | 10 | 0 |

**恢复 20 个正向锚点并不等于解析准确率提升 20 项**。这些只是训练前的数据对齐结果，不是模型预测、语义真实性或生产表现。

复现：

    uv run --python 3.12 python -m scripts.benchmark_span_supervision
    uv run --python 3.12 python -m pytest tests/test_span_supervision.py tests/test_line_field_classifier.py tests/test_line_field_experiment.py -q

## 下一阶段的唯一里程碑

设计能从 PDF 原文和几何信息中，**不看 GT 地提出职位/公司字符片段**的提议器；独立 GT 只用于训练及随后验收，未知区间不能擅自当负例。先在开发分组证明超过同预算词表方案，再决定是否启用编号 41–60 的全新保留集。只在端到端 PDF→Schema 有净增益、原文来源可追溯、不新增虚构任职、需要人工确认时才考虑产品接入。

本轮没有 GPU、外部收费 AI、实际求职者数据、模型持久化、生产 API 修改或 GitHub 推送。
