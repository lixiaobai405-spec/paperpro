# PaperPro：成熟版式解析器隔离对照（2026-10-19）

**结论：实际对照已完成，但 PyMuPDF4LLM 的当前 JSON→WorkBlock 适配器效果弱于原生 PyMuPDF。不得接入生产。**

## 版本、许可与隔离

现有 PaperPro 使用 PyMuPDF 1.28.2。当前 PyPI 的 pymupdf4llm 2.0 是没有导入模块的空兼容包，4LLM 功能已迁入 PyMuPDF 2.x。因此直接使用最新包会出现 ModuleNotFoundError，并非文档解析失败。

本轮锁定 pymupdf4llm==1.28.2，以 uv --with 在独立依赖 overlay 中运行。没有使用 uv add，也没有修改 pyproject.toml、uv.lock 或生产 .venv。该库属于 AGPL/商业双许可，此处仅做隔离内部研究，不打包、不分发、不并入商业产品；如需商业集成必须确认许可证与交付义务。

Docling 和 PaddleOCR 尚未安装，也尚未做真实模型比较。本轮是一个较轻量的成熟版式工具的第一项实际对照，不能冒充 Docling 实测。

## 任务设计

使用 Apache-2.0 开源合成 PDF SyntheticResumeData，固定 commit：

3ecd09129f65955e743aacf67f2785fcee10d461

**仅使用 21–35 号的 15 份训练开发 PDF**。36–40 验证、41–60 全新冻结测试，以及历史固定 1–10、101–105、201–205 挑战集均未读取。模型先只根据 PDF 原生文字和 PyMuPDF4LLM 的 JSON 版式对象产生候选 WorkBlock，随后才使用独立 GT 评测。

app/diagnosis/layout_workblocks.py 只接受 JSON 数据，不导入第三方包；识别原文行、坐标、已知章节与日期，处理明确平行栏目。遇到新的未知章节也会关闭工作区域。所有 WorkBlock 仅是未经确认的来源区段：不生成真实工作经历、公司/职位结论、任期分数，不改上传文件。

scripts/benchmark_layout_workblocks.py 实现相同开发池、相同独立 GT 的比较。

## 真实结果：15 份 PDF，32 组公司—职位配对

| 指标 | 本轮 |
|---|---:|
| 成功执行第三方布局引擎 | 15/15 PDF |
| PyMuPDF4LLM layout box | 382 |
| 识别出的工作章节 | 10 |
| 识别为独立平行双栏的页面 | 2 |
| JSON 版式生成的 WorkBlock | 9 |
| 同一 WorkBlock 包含 GT 公司+职位 | **9/32（28.13%）** |
| 同块公司、职位、起止年月一致 | **9/32（28.13%）** |

在完全相同的 15 份 PDF、32 组 GT 上，此前已经固定的参照为：

| 方法 | GT 公司职位同一源区域 |
|---|---:|
| 旧线性解析器的原文工作 Entry | **19/32（59.38%）** |
| PyMuPDF 原生坐标 WorkBlock | **17/32（53.13%）** |
| 本轮 PyMuPDF4LLM JSON→WorkBlock | **9/32（28.13%）** |

这是**原文共现/区域候选覆盖**，不是字段提取精确率。较差结果可能由当前模型输出到 WorkBlock 的映射丢失区域归属造成，不能断言整个 PyMuPDF4LLM 或 Docling 不具备更好版式理解能力。可以明确断言的是：本轮适配器没有提供可用于产品的净收益。

**验收门禁：不替换原生解析、不进行双路自动合并、不部署、不改评分。**

## 复现

不需要第三方依赖即可运行的纯适配器和安全测试：

    uv run --python 3.12 python -m pytest tests/test_layout_workblocks.py tests/test_layout_workblock_benchmark.py -q

实际版式引擎对照（只向 uv 注入隔离依赖）：

    uv run --python 3.12 --with 'pymupdf4llm==1.28.2' python -m scripts.benchmark_layout_workblocks

输出仅为匿名汇总与数据集编号，不包含 PDF 原文、姓名、电话、公司或职位。GitHub 项目仓库未更新，外部原始数据不进 Git。

## 后续消融：确认主要损失发生在语义章节适配

仍用同一 15 份训练开发 PDF、32 组独立 GT；这是新增的阶段损失归因，不是对新的冻结集的测试。

原生 PyMuPDF 文字行可找到 31/32 组公司及职位文本；PyMuPDF4LLM 1.28.2 版式 JSON 文字行可找到 29/32 组；但旧 JSON→WorkBlock 映射仅有 9/32 组进入同一区域。29 组保留的文本里有 20 组在后续区域适配阶段丢失。

模型产生 91 个标题类型 box，但仅识别出 10 个工作章节。它的 section-header、title、chapter-header 是**排版类别而非必然的语义章节**。原来的保守适配器一律用它们终止当前工作区，导致大量误截断。

仅在实验层新增 unknown_heading_policy="keep"（默认仍为 close），已知项目/教育章节始终终止工作区。实测：

| 处理方式 | 同 WorkBlock 的 GT 配对 | 候选 WorkBlock | 缺少 GT 配对支持的候选 |
|---|---:|---:|---:|
| 旧版所有模型标题截断 | 9/32 | 9 | 0 |
| 实验版只在已知其他章节处截断 | **17/32** | 27 | **11** |
| 原生 PyMuPDF WorkBlock | **17/32** | 25 | 旧开发实验另行记录 |

**新实验版与原生 PyMuPDF 命中完全相同的 17 组配对，两者并集仍为 17/32，相对原生引擎的独有增益为 0。** 额外 11 个候选没有当前 GT 配对证据，不得直接断定是假任职，但也不能自动采纳。默认策略不变、正式 API 和五维评分不变；不以本次消融对外宣称端到端解析准确率提高。

复验：

    uv run --python 3.12 --with 'pymupdf4llm==1.28.2' python -m scripts.diagnose_mature_layout_loss
    uv run --python 3.12 python -m pytest tests/test_layout_workblocks.py tests/test_layout_loss_diagnostics.py -q

不读取 36–40、41–60 或历史固定外部挑战集。GT 在候选生成后才读取，日志无原始履历和姓名。

## 下一最短有效路径

1. 使用独立、此前未被用于定向修改的开发样本，对 Docling 的文档区域分类及章节归属进行**模型级**对照。需要评估实际安装/模型下载成本和 AGPL/商业许可边界。
2. 保留现有线性解析为基础，预训练版式引擎仅作为受约束的区域证据。不要再次将整页全局重排或以“多产出 WorkBlock”为优化目标。
3. 必须最终检验 GT 的同一工作条目内 company/role/start/end 正确归属，以及不存在虚构任职。区域共现不是最终的字段准确率。

PaperPro 的固定外部 20 PDF→Schema 基准仍为 **167/276（60.51%）**，本轮未改动正式产品。
