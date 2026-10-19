# PaperPro · 智能简历诊断与增强工作台

PaperPro 现有两条独立但共用解析与设置基础设施的流程：**求职者端五维诊断**（默认入口）和**经典简历编辑**（保留原功能）。上传数据默认本机处理；从不自动改写用户上传的原始文件。

## 快速使用

当前 Windows 电脑已安装依赖并完成前端构建，网页服务监听：

**http://127.0.0.1:8766/**

双击项目根目录的 **start-paperpro.cmd** 可在服务未启动时启动服务（需保持命令行窗口开启）。默认仅绑定 127.0.0.1，不能被其他设备直接访问。

如果要从零安装，在本目录执行：

    uv sync --python 3.12 --group dev
    cd frontend
    npm ci
    npm run build
    cd ..
    uv run --python 3.12 python -m uvicorn app.main:app --host 127.0.0.1 --port 8766

不得使用 Anaconda/Miniconda；Python 由 uv 管理。前端采用 React + Vite + Mantine + Tabler Icons，后端 FastAPI + RapidOCR + PyMuPDF + python-docx。Microsoft Word 负责高保真 DOCX→PDF 和旧版 DOC 读取；当 Word 不可用时有基础 PDF 备用引擎，极罕见非 BMP 字符会明确拒绝错误导出。

## 求职者端 · 五步诊断（默认首页）

地址：**http://127.0.0.1:8766/**。按 ① 上传 PDF/DOCX/DOC/PNG/JPG（单文件 10 MB）或粘贴文本 → ② 校对可编辑的公司、职位、年月、技能、教育和证书 → ③ 填写目标职位和/或目标公司（推荐附真实 JD） → ④ 查看五大 HR 视角诊断与溯源证据 → ⑤ 逐条勾选建议或核查问题、仅导出选中内容（TXT/PDF）。

五大结果分别是岗位匹配证据覆盖度（七类因子、0–1 系数与可配置权重）、工作经验时间线（相关任职去重月份与空档）、学习潜力证据信号、岗位针对性和有位置的核查疑点。优化建议在满足不少于 8 项的同时，区分有依据的「需要修正」和「可选深化」；符合要求的经历不会被无故标为时间或成果硬伤，选中清单会保留类别。默认纯本地确定性规则；DeepSeek 辅助解读只有明确同意后才会外发，且**只能选择规则表中的解释模板与已存在的证据路径**。自然语言由本地模板生成，不能覆盖算法算出的时间、得分或自行编写公司/学历事实。

**解析质量工程验收**：新增 20 份合成 DOCX/PDF（260/260 字段正确）与 4 张清晰合成 PNG/JPEG（49/52 字段正确，94.23%）的本地基准，以及 Android/iPhone 浏览器模拟、Chrome 实际扫描上传→OCR→诊断链路。运行：`uv run --python 3.12 python -m scripts.benchmark_resume_parsing --include-ocr`。这**不是实际简历或手机真机准确率**；具体失败项及边界见 `docs/SYNTHETIC_PARSER_QA.md`。

规则权重和高/中/低阈值仍属**初版假设**。已完成 48 个合成层级情景、±20% 权重扰动测试，以及 1,680 组独立反事实关系的压力测试（`uv run --python 3.12 python -m scripts.stress_test_scoring`），据此修复了重复证据刷分和技能词表遗漏。但尚缺独立 HR 标注样本与真实筛选结果，**不能把分数写成录用概率或已验证的 HR 官方打分**。详情见 `docs/SCORING_METHODOLOGY.md` 和 `docs/R7_R10_CANDIDATE_DIAGNOSIS.md`。已提供完全离线的专家评分评价脚本：`uv run --python 3.12 python -m scripts.evaluate_hr_dataset --input evaluation_private/hr_labels.json`；私密数据集不会被 Git 跟踪。

## 经典简历编辑（/classic）

地址：**http://127.0.0.1:8766/classic**。

1. 拖拽上传一个 PDF、DOCX、DOC、PNG 或 JPG（最大 12 MB；PDF 最多 25 页）。
2. OCR 自动处理扫描图片和 PDF 内较大的图片文字。请核对识别提醒。
3. 在左侧修正姓名、联系信息、简介、技能、经历、项目与教育，右侧同步显示 A4 样式预览。
4. 选择本地安全整理；或者选择 AI 智能润色 → DeepSeek（默认）或自定义 API，并明确授权和提供该服务商的 Key。
5. 展开“查看原始识别文本”，对照原文核实数字、时间、公司、学校和措辞，勾选确认后导出 Word/PDF。

**重要边界：** 本地模式只清理排版/行文中的空白及列表符号，不包含大模型的语义重写；外部 AI 模式可以增强表达，但定性事实可能出错，必须逐项核实。数字变化、履历项数量变化和身份字段修改受到后端约束，但这不能代替人的事实核对。生成的结果始终属于可编辑草稿。

## 固定配置文件 settings.json

项目根目录的 **settings.json 是可提交 GitHub 的公共配置模板**。其中 `deepseek.api_key` 和 `configured.api_key` 最终都保留为空字符串 `""`；旁边的 `_api_key_comment` 说明了用途。标准 JSON 不支持 `//` 注释，所以使用 `_comment` 字段。

要在**本机长期保存 DeepSeek Key**，推荐新建根目录的 **settings.local.json**（已加入 `.gitignore`，不会提交 GitHub），内容只需要：

    {
      "deepseek": { "api_key": "粘贴你自己新生成的密钥" }
    }

如果不想在磁盘持久保存密钥，仍可以在网页右上角「AI 设置」中填写，刷新页面后失效。DeepSeek 永远使用官方 https://api.deepseek.com/v1 和模型 deepseek-flash，避免误把密钥发往其他服务。网页选择「AI 智能润色 → DeepSeek」，勾选发送授权后即可调用。**不要把真实密钥写入公开仓库、截图或聊天消息。**

**配置优先级**：当前页面输入 > `settings.local.json` > 旧环境变量 > `settings.json`。服务每次请求重新读取 JSON，修改本地配置一般不需要重启；刷新网页可以更新「已配置密钥」提示。

如果需要用环境变量临时配置 DeepSeek，仍支持 `PAPERPRO_DEEPSEEK_API_KEY`。


**自定义 OpenAI 兼容 API：** 在网页选择「自定义 API」，在 PowerShell 中设置会话级环境变量并启动服务：

    $env:PAPERPRO_OPENAI_API_KEY = "你的密钥"
    $env:PAPERPRO_OPENAI_MODEL = "gpt-4.1-mini"
    $env:PAPERPRO_OPENAI_BASE_URL = "https://api.openai.com/v1"
    uv run --python 3.12 python -m uvicorn app.main:app --host 127.0.0.1 --port 8766

自定义服务也可在 `settings.local.json` 的 `configured` 区域配置 `api_key`、`base_url` 和 `model`。网页输入的密钥只存在当前页面内存里，不写入磁盘。只有主动点击 AI 润色并勾选同意才会发送简历文字；未提供对应服务商的密钥时会明确报错。外部服务的数据处理政策以对应服务商为准。

## 测试与验收

在根目录执行后端单元、文档、OCR、安全、API 和模板回归：

    uv run --python 3.12 python -m pytest -q --cov=app --cov-report=term-missing

启动后端服务以后，在 frontend 下执行真实 Chrome E2E：

    cd frontend
    npm test -- --project=chromium

测试使用本机已安装的 Google Chrome，不需要 Playwright 另装 Chromium。构建：进入 frontend 并执行 npm run build。2026-10-19 的新版五步流程与原编辑器共 **23 项 Chrome E2E 通过**；后端覆盖率 **90%**。原有 Word COM 测试仍可能打印 Windows RPC 异常，需在目标机器持续关注。

**尚未通过真实数据验收：** 20 份授权简历的字段完整率、清晰手机照片 OCR 准确率、真实 iOS/Android 原生文件选择、两个其他智能体的风格走查、真实 HR 标注一致性及预测效度。不要以合成数据代替这些验收。

DOCX/PDF 渲染验收使用合成数据，文件位于 artifacts/visual/（自动忽略版本控制，浏览器测试也不会将它们清除）。AI 接口除了模拟响应的回归测试，还在 2026-10-18 用一次真实 DeepSeek 后端请求和一次真实 Chrome 用户流程验收：均返回 HTTP 200，Chrome 实际生成 3 处建议、人工选择并应用、下载 Word/PDF。测试只发送虚构简历，密钥通过临时标准输入注入测试进程，没有保存到文件。此验收不意味着模型对任意简历都不会虚构事实，用户仍须审核。

## 文件与模块

- **SPEC.md** — 需求、正确性约束、反例与验收标准
- **app/parser.py** — Word/PDF/图片提取、OCR、结构化解析
- **app/diagnosis/rules.json** — 五维判定条件、岗位族群、权重和阈值的共同规则源
- **app/diagnosis/scoring.py** — 可复现岗位证据计分与任职时间去重
- **app/diagnosis/calibration.py** — 合成排序、扰动、AHP/Swing 和独立 HR 标注评估
- **app/diagnosis/engine.py** — 五大诊断、优化建议、面试核查清单
- **app/diagnosis/api.py** — 10 MB 上传、粘贴解析、报告和选中项导出
- **frontend/src/CandidateDiagnosisApp.jsx** — 视频参考样式的五步求职者端诊断页面
- **app/models.py** — 履历结构与请求格式
- **app/enhancer.py** — 本地清理与可选 AI 润色、数字检查
- **app/exporter.py** — 唯一固定 Word 模板与 PDF 转换
- **app/main.py** — 端到端 API 和前端静态资源
- **settings.json** — 公共、无真实密钥的固定配置模板；空值与说明
- **settings.local.json** — 本机私密覆盖文件（自行创建，Git 忽略）
- **app/settings.py** — 配置解析、优先级、服务商密钥隔离
- **frontend/src/App.jsx** — 上传、编辑、核验、润色、导出工作流
- **frontend/src/styles.css** — 工作台视觉与移动端排版
- **tests/**、**frontend/e2e/** — 回归和浏览器测试

## 隐私与局限

服务端不设数据库、不保存简历记录，也**不会自动保存网页输入的 API Key**。如果你主动在本机 `settings.local.json` 中填入密钥，它会作为私人文件长期保存在磁盘中，须自行保护；该文件不会上传 GitHub。上传数据在每个请求中处理，Word 转换仅使用操作系统临时目录并在正常结束时清理；浏览器刷新后未导出的草稿会丢失。不要上传没有权限处理的第三方私人资料。

某些复杂表格、图片中的低分辨率文字、混排页面或罕见字体可能需要手动修正；原始识别文本始终可展开核对。PDF/PPT 风格的多栏简历可能无法自动恢复原布局：本项目的目标是统一生成固定模板，而非逐像素复刻原件。Watchdog 用于监督本次开发对话，不是简历网页的后台服务。
