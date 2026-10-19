# R7/R8 独立标注到 PDF 源行与关系监督接口

日期：2026-10-19

## 固定数据边界

- 外部数据：Apache-2.0 项目 jijunhao/SyntheticResumeData。
- Git commit：3ecd09129f65955e743aacf67f2785fcee10d461。
- 开发候选池：公开合成 PDF 编号 21–40，共 20 份。
- 固定外部挑战集（禁止训练和挑选参数）：1–10、101–105、201–205，共 20 份。
- 字段标注来自第三方公开数据，不来自 PaperPro 的评分预测。
- PDF 与标注内容只在内存处理；不写入产品仓库、不在日志输出任何简历原文、姓名、联系方式或公司/职位文本。

## 数据访问恢复

首次使用 GitHub REST Contents API 读取开发池时，在编号 30 遇到 403 配额限制。本机全局 Git 配置还把 GitHub HTTPS 重写为 SSH，部分克隆按需抓取缺失 Blob 时会阻塞。

已实现只在取样子进程中设置 GIT_CONFIG_GLOBAL=os.devnull，暂时屏蔽全局 Git URL 重写，原来的固定 commit 与 HTTPS origin 保持不变，缺失的 Git Blob 仍缓存于系统 Temp 目录下的独立部分克隆。不重新克隆、不修改全局 Git 设置、不存入 PaperPro。路径见 scripts/benchmark_annotation_alignment.py。相关红→绿测试已通过。

## 不依赖预测模型的 PDF 文字行对齐

由 PyMuPDF 提取原生文字行与归一化坐标。对于每条独立 GT 标注：
- 仅在唯一文字行匹配时记录 source anchor。
- 找不到和多次匹配保留为未确定，不能当负样本。
- 输出的聚合数字不含身份证据或个人简历文本。
- 重复来源锚点不得产生错误的正负配对。

| 指标 | 开发池（21–40） | 固定挑战集 |
|---|---:|---:|
| 职位唯一文字行 | 33/45（73.33%） | 36/50（72.00%） |
| 公司唯一文字行 | 42/46（91.30%） | 40/49（81.63%） |
| 学校唯一文字行 | 17/27（62.96%） | 18/22（81.82%） |
| 独立 GT 公司—职位配对 | 45 | 49 |
| 两端同时唯一定位 | 33/45（73.33%） | 32/49（65.31%） |
| 同页 | 33/45 | 32/49 |
| 同一视觉行 | 30/45（66.67%） | 27/49（55.10%） |

来源：app/diagnosis/annotation_alignment.py，scripts/benchmark_annotation_alignment.py。相同代码分别运行以下命令：

    uv run --python 3.12 python -m scripts.benchmark_annotation_alignment --split train_candidate_feasibility
    uv run --python 3.12 python -m scripts.benchmark_annotation_alignment --split holdout_evaluation

以上表示 GT 字段在 PDF 上的文字位置可寻找程度，不证明职位与公司的真实对应关系。

## CPU 关系排序实验（参数化但不部署）

app/diagnosis/relation_pairs.py 只用独立 GT 的同一 workExperience 条目标记公司—职位正例。若另两个 GT 条目都有唯一锚点且不存在重复公司或重复职位，才允许构造跨条目对照。未知/缺失文本不能自动成为负例。

app/diagnosis/relation_ranker.py 使用六个固定的几何特征和确定性的 L2 线性 Logistic 回归进行小型 CPU 拟合。与无需训练的几何基线做并行对照。没有下载模型，没有使用 GPU，没有保存模型参数，也没有接入正式评分和上传接口。

| 指标 | 训练候选池 | 冻结挑战集 |
|---|---:|---:|
| 关系样本 | 69 | 70 |
| 正例/跨条目对照 | 33/36 | 32/38 |
| 有跨条目对照的 PDF | 14/20 | 13/20 |
| 无训练几何基线，非平凡 Top-1 | 30/30 | 29/29 |
| 线性参数化排序器，非平凡 Top-1 | 30/30 | 29/29 |
| 相比不训练基线的净收益 | 0 | 0 |

**不能宣传端到端简历解析 100% 或真实招聘准确率。** 这里使用第三方 GT 唯一锚点作为候选来源，省略了原始 PDF 自动寻找这些字段这一最难环节。在此附加条件下问题对纯坐标方法已经太简单，训练参数没有带来收益。不能将这种条件化的关系 Top-1 替代产品外部固定挑战集的结构化命中率 167/276（60.51%）。

复现：

    uv run --python 3.12 python -m scripts.benchmark_relation_pairs --split train_candidate
    uv run --python 3.12 python -m scripts.benchmark_relation_pairs --split holdout_evaluation
    uv run --python 3.12 python -m scripts.experiment_relation_ranker
    uv run --python 3.12 python -m pytest tests/test_pdf_annotation_alignment.py tests/test_relation_pairs.py tests/test_relation_ranker.py -q

## 后续最短里程碑

必须让新抽取器在不知道 GT 的情况下，从原生 PDF 文字行与版面中**自动产生公司、职位候选**，并使用独立标注评价候选召回率、误报率与完整经历关系是否正确。不得直接把未标注文字行当错误负例，不得自动确认低置信度职位，不得使用固定挑战集训练或选择超参数。

产品自动抽取的接受标准必须回到原定的 20 份固定 PDF、276 项 GT：与 167/276 的旧版基准比，先证明净增益，再核实不制造虚构任职或污染日期。若不能证明，则保持 R7 的人工核对通道。

当前状态：数据接口和小规模 CPU 实验完成；正式自动职位关系抽取仍未达到发布验收门槛。
