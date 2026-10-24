import { useEffect, useRef, useState } from 'react';
import {
  Accordion, ActionIcon, Alert, Badge, Box, Button, Checkbox, Divider, FileButton,
  Grid, Group, Loader, Modal, Paper, ScrollArea, SegmentedControl, SimpleGrid,
  Stack, Text, Textarea, TextInput, ThemeIcon, Title, Tooltip,
} from '@mantine/core';
import { Dropzone } from '@mantine/dropzone';
import {
  IconAlertTriangle, IconArrowRight, IconCircleCheck, IconCloudUpload, IconDownload,
  IconFileDescription, IconFileTypeDocx, IconFileTypePdf, IconFileTypePng, IconFileUpload,
  IconInfoCircle, IconLock, IconPlus, IconRefresh, IconSettings, IconShieldCheck,
  IconSparkles, IconTrash, IconWand, IconX,
} from '@tabler/icons-react';
import { consumeClassicHandoff } from './resumeHandoff.js';

const EMPTY = {
  name: '', title: '', phone: '', email: '', location: '', links: [],
  summary: '', skills: [], experience: [], projects: [], education: [], additional: [],
};

const DEMO = {
  name: '陈晓明', title: '后端开发工程师', email: 'demo@example.com',
  phone: '138 0000 0000', location: '广东 · 深圳', links: ['github.com/example'],
  summary: '拥有3年后端系统研发经验，熟悉Python、FastAPI与数据库设计，注重系统稳定性和团队协作。',
  skills: ['Python', 'FastAPI', 'MySQL', 'Redis', 'Docker', 'Git'],
  experience: [
    { heading: '2022.07 – 2025.06  星辰科技  |  后端开发工程师',
      bullets: ['参与订单管理系统后端开发，优化核心接口响应时间20%', '设计和维护业务数据库表结构，支持日常功能迭代'] },
  ],
  projects: [
    { heading: '订单分析平台  |  Python / MySQL',
      bullets: ['构建订单数据统计模块，为业务分析提供可复用的数据接口'] },
  ],
  education: [{ heading: '2018.09 – 2022.06  华南理工大学  |  计算机科学与技术学士', details: [] }],
  additional: ['英语 CET-6'],
};

const FORMATS = '.pdf,.doc,.docx,.png,.jpg,.jpeg';
const ACCEPT = {
  'application/pdf': ['.pdf'],
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
  'application/msword': ['.doc'],
  'image/png': ['.png'],
  'image/jpeg': ['.jpg', '.jpeg'],
};

async function requestJson(path, payload) {
  const response = await fetch(path, payload === undefined ? undefined : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || '服务暂时不可用，请检查本地服务状态');
  return body;
}

function splitLines(text) {
  return text.split(/\r?\n/).map((x) => x.trim()).filter(Boolean);
}

function splitValues(text, delimiter = 'lines') {
  return text.split(delimiter === 'lines' ? /\r?\n/ : /[，,、;\n]/).map((x) => x.trim()).filter(Boolean);
}

// Keep the exact characters the user is typing (including a trailing comma
// or newline) while continuously updating the structured preview.
function DelimitedField({ values, onChange, delimiter = 'lines', ...props }) {
  const separator = delimiter === 'lines' ? '\n' : '，';
  const [draft, setDraft] = useState((values || []).join(separator));
  const [focused, setFocused] = useState(false);
  const canonical = (values || []).join(separator);
  useEffect(() => {
    if (!focused) setDraft(canonical);
  }, [canonical, focused]);
  const isMultiline = delimiter === 'lines';
  const Field = isMultiline ? Textarea : (props.multiline ? Textarea : TextInput);
  const { multiline, ...fieldProps } = props;
  return (
    <Field {...fieldProps} value={draft}
      onFocus={() => setFocused(true)}
      onChange={(event) => {
        const raw = event.currentTarget.value;
        setDraft(raw);
        onChange(splitValues(raw, delimiter));
      }}
      onBlur={() => {
        setFocused(false);
        setDraft((values || []).join(separator));
      }}
    />
  );
}

function SectionLabel({ children, hint }) {
  return (
    <Group gap={8} mt="sm" mb="xs" align="center">
      <Text className="field-section-heading">{children}</Text>
      {hint && <Text size="xs" c="dimmed">{hint}</Text>}
    </Group>
  );
}

function EntryEditor({ title, entries, onChange, onAdd, onRemove, kind = 'entry', headingComparisons = [] }) {
  const detailKey = kind === 'education' ? 'details' : 'bullets';
  return (
    <section className="editor-subsection" data-testid={title}>
      <Group justify="space-between" mb="xs">
        <Text fw={650} size="sm">{title} <span className="muted-counter">{entries.length}</span></Text>
        <Button variant="subtle" size="compact-sm" leftSection={<IconPlus size={14} />} onClick={onAdd}>添加</Button>
      </Group>
      {entries.length === 0 && <Text className="empty-line">暂无内容。添加后会自动出现在模板中。</Text>}
      <Stack gap="sm">
        {entries.map((entry, index) => (
          <Paper key={index} withBorder p="sm" radius="md" className="entry-card">
            <Group gap={8} justify="space-between" mb={8}>
              <Text size="xs" c="dimmed" fw={600}>第 {index + 1} 条</Text>
              <Tooltip label="删除此条">
                <ActionIcon variant="subtle" color="red" aria-label="删除此条" size="sm" onClick={() => onRemove(index)}>
                  <IconTrash size={15}/>
                </ActionIcon>
              </Tooltip>
            </Group>
            <Stack gap={8}>
              <TextInput
                size="sm"
                label={kind === 'education' ? '学校、学历及起止时间' : '机构、角色及起止时间'}
                value={entry.heading}
                onChange={(event) => onChange(index, 'heading', event.currentTarget.value)}
                placeholder={kind === 'education' ? '2020–2024 XX大学 | XX专业' : '2023–2025 XX公司 | 软件工程师'}
              />
              {headingComparisons.filter((comparison) => comparison.index === index).map((comparison) =>
                <div data-testid={'handoff-heading-comparison-' + index} key={index}>
                  <Text size="xs" c="orange" mb="xs">
                    校对阶段保留的标题与当前标题不同。请核对是否遗漏部门、工作性质等信息；
                    该标题可能已在校对阶段被修改，初始文件证据请查看「原始识别文本」。只有当前编辑标题会进入导出。
                  </Text>
                  <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="xs">
                    <Paper p="xs" withBorder radius="sm">
                      <Text size="xs" c="dimmed" fw={700}>校对阶段标题（不自动导出）</Text>
                      <Text size="sm">{comparison.original}</Text>
                    </Paper>
                    <Paper p="xs" withBorder radius="sm">
                      <Text size="xs" c="dimmed" fw={700}>当前标题（将用于导出）</Text>
                      <Text size="sm">{entry.heading}</Text>
                    </Paper>
                  </SimpleGrid>
                </div>
              )}
              <DelimitedField
                size="sm" autosize minRows={2} maxRows={6}
                label={kind === 'education' ? '补充内容（一行一项）' : '工作内容 / 成果（一行一项）'}
                values={entry[detailKey] || []}
                onChange={(next) => onChange(index, detailKey, next)}
                placeholder="描述具体的职责、行动和可验证结果"
              />
            </Stack>
          </Paper>
        ))}
      </Stack>
    </section>
  );
}

function PreviewSection({ title, children }) {
  return <section className="paper-section">
    <h3>{title}</h3>
    <div className="paper-section-content">{children}</div>
  </section>;
}

function ResumePreview({ resume }) {
  if (!resume) return (
    <div className="paper-sheet paper-placeholder" data-testid="resume-preview-empty">
      <div className="placeholder-icon"><IconFileDescription size={34} stroke={1.4}/></div>
      <h3>你的新简历，将在这里成形</h3>
      <p>上传文件后，右侧会实时显示统一的 A4 排版效果。</p>
      <div className="placeholder-lines" aria-hidden="true">
        <span/><span/><span/><span/><span/><span/><span/>
      </div>
    </div>
  );
  return (
    <article className="paper-sheet" data-testid="resume-preview">
      <header className="paper-head">
        <h1>{resume.name || '请填写姓名'}</h1>
        {resume.title && <p className="paper-role">{resume.title}</p>}
        <div className="paper-contact">
          {[resume.phone, resume.email, resume.location, ...(resume.links || [])].filter(Boolean).map((c, i) => <span key={i}>{c}</span>)}
        </div>
      </header>
      {resume.summary && <PreviewSection title="个人简介  /  PROFILE">
        {resume.summary.split('\n').filter(Boolean).map((line, i) => <p key={i}>{line}</p>)}
      </PreviewSection>}
      {resume.skills?.length > 0 && <PreviewSection title="专业技能  /  SKILLS">
        <p className="paper-skills">{resume.skills.join('  ·  ')}</p>
      </PreviewSection>}
      {resume.experience?.length > 0 && <PreviewSection title="工作经历  /  EXPERIENCE">
        {resume.experience.map((entry, idx) => <div className="paper-entry" key={idx}>
          <p className="paper-entry-title">{entry.heading}</p>
          <ul>{entry.bullets?.map((bullet, i) => <li key={i}>{bullet}</li>)}</ul>
        </div>)}
      </PreviewSection>}
      {resume.projects?.length > 0 && <PreviewSection title="项目经历  /  PROJECTS">
        {resume.projects.map((entry, idx) => <div className="paper-entry" key={idx}>
          <p className="paper-entry-title">{entry.heading}</p>
          <ul>{entry.bullets?.map((bullet, i) => <li key={i}>{bullet}</li>)}</ul>
        </div>)}
      </PreviewSection>}
      {resume.education?.length > 0 && <PreviewSection title="教育背景  /  EDUCATION">
        {resume.education.map((entry, idx) => <div className="paper-entry" key={idx}>
          <p className="paper-entry-title">{entry.heading}</p>
          {entry.details?.map((line, i) => <p key={i}>{line}</p>)}
        </div>)}
      </PreviewSection>}
      {resume.additional?.length > 0 && <PreviewSection title="其他信息  /  ADDITIONAL">
        <ul>{resume.additional.map((line, i) => <li key={i}>{line}</li>)}</ul>
      </PreviewSection>}
    </article>
  );
}

function Header({ config, onSettings }) {
  return <header className="topbar">
    <div className="brand-group">
      <div className="brand-mark"><span>P</span></div>
      <div>
        <div className="brand-name">paper<span>pro</span></div>
        <div className="brand-caption">RESUME STUDIO</div>
      </div>
      <span className="brand-divider"/>
      <span className="brand-product">智能简历工作台</span>
    </div>
    <Group gap="sm" wrap="nowrap">
      <div className="privacy-pill"><IconLock size={14}/><span>本地优先 · 隐私保护</span></div>
      <Tooltip label="AI 服务设置">
        <ActionIcon size={38} variant="default" aria-label="AI 设置" onClick={onSettings}><IconSettings size={19}/></ActionIcon>
      </Tooltip>
    </Group>
  </header>;
}

function WorkflowSteps({ state }) {
  const items = [
    ['01', '导入材料'], ['02', '审核并润色'], ['03', '导出简历'],
  ];
  return <div className="flow-steps">{items.map(([n, label], i) => (
    <div className={'flow-step ' + (i <= state ? 'is-active' : '')} key={n}>
      <span className="step-number">{i < state ? <IconCircleCheck size={16}/> : n}</span>
      <span>{label}</span>
      {i < 2 && <span className="step-connector" aria-hidden="true"/>}
    </div>
  ))}</div>;
}

export default function App() {
  const [resume, setResume] = useState(null);
  const [source, setSource] = useState('');
  const [fileMeta, setFileMeta] = useState(null);
  const [changes, setChanges] = useState([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [reviewed, setReviewed] = useState(false);
  const [config, setConfig] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [mode, setMode] = useState('local');
  const [provider, setProvider] = useState('deepseek');
  const [apiKey, setApiKey] = useState('');
  const [targetRole, setTargetRole] = useState('');
  const [jobDescription, setJobDescription] = useState('');
  const [aiConsent, setAiConsent] = useState(false);
  const [pendingAi, setPendingAi] = useState(null);
  const [documentToken, setDocumentToken] = useState(0);
  const [handoffAdvice, setHandoffAdvice] = useState([]);
  const [handoffHeadingComparisons, setHandoffHeadingComparisons] = useState([]);
  const editVersion = useRef(0);
  const fileSelectionVersion = useRef(0);

  useEffect(() => {
    // The candidate flow explicitly hands off one draft, in this tab only.
    // No previous approvals, pending AI output, or upload lifecycle survive.
    let transfer = null;
    try { transfer = consumeClassicHandoff(window.sessionStorage); } catch { /* storage disabled */ }
    if (!transfer) return;
    editVersion.current += 1;
    fileSelectionVersion.current += 1;
    setDocumentToken((version) => version + 1);
    setResume({ ...EMPTY, ...transfer.resume });
    setTargetRole(transfer.targetRole || '');
    setJobDescription(transfer.jobDescription || '');
    setSource(transfer.sourceText || '');
    setFileMeta({
      filename: transfer.filename || '已校对的诊断简历',
      method: '诊断流程交接',
      warnings: [
        '工作经历标题已按校对后的年月、公司与职位整理，导出前请对照原文再次核实。',
        ...(transfer.targetCompany ? ['目标公司：' + transfer.targetCompany] : []),
      ],
    });
    setHandoffAdvice(transfer.advice);
    setHandoffHeadingComparisons(
      (Array.isArray(transfer.headingComparisons) ? transfer.headingComparisons : [])
        .filter((item) => Number.isInteger(item?.index)
          && item.index >= 0 && item.index < transfer.resume.experience.length
          && typeof item.original === 'string' && typeof item.projected === 'string')
    );
    setChanges([]);
    setPendingAi(null);
    setReviewed(false);
    setAiConsent(false);
    setMode('local');
  }, []);

  useEffect(() => {
    fetch('/api/config').then((r) => r.ok ? r.json() : null).then(setConfig).catch(() => {});
  }, []);

  function mutate(next, touched) {
    editVersion.current += 1;
    setResume((previous) => typeof next === 'function' ? next(previous) : next);
    setReviewed(false);
    setPendingAi(null);
    // Preserve the comparison for unrelated fields.
    setChanges((previous) => previous.filter((change) =>
      touched && change.field !== touched && !change.field.startsWith(touched + '.')
    ));
  }
  function updateField(field, value) {
    mutate((previous) => ({ ...previous, [field]: value }), field);
  }
  function updateEntry(key, index, field, value) {
    mutate((previous) => ({
      ...previous,
      [key]: previous[key].map((entry, i) => i === index ? { ...entry, [field]: value } : entry),
    }), key + '.' + index + '.' + field);
  }
  function addEntry(key) {
    const entry = key === 'education' ? { heading: '', details: [] } : { heading: '', bullets: [] };
    mutate((previous) => ({ ...previous, [key]: [...previous[key], entry] }), key);
  }
  function removeEntry(key, index) {
    mutate((previous) => ({ ...previous, [key]: previous[key].filter((_, i) => i !== index) }), key);
    if (key === 'experience') {
      // The editor has no reordering control: a deletion shifts later indices.
      // Keep source comparisons bound to their remaining work entry.
      setHandoffHeadingComparisons((previous) => previous
        .filter((item) => item.index !== index)
        .map((item) => item.index > index ? { ...item, index: item.index - 1 } : item));
    }
  }

  async function uploadFile(file) {
    if (!file) return;
    // File selection owns the replacement lifecycle. Editing the AI brief
    // must not cancel an already selected file's extraction.
    const uploadVersion = ++fileSelectionVersion.current;
    editVersion.current += 1;
    setPendingAi(null);
    setError('');
    if (file.size > 12 * 1024 * 1024) {
      setError('文件超过 12 MB，请压缩后重新上传。'); return;
    }
    setBusy('extract');
    const data = new FormData();
    data.append('file', file);
    try {
      const response = await fetch('/api/extract', { method: 'POST', body: data });
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.detail || '识别失败，请换一种文件格式');
      if (uploadVersion !== fileSelectionVersion.current) return;
      setDocumentToken((version) => version + 1);
      setResume({ ...EMPTY, ...result.resume });
      setHandoffAdvice([]);
      setHandoffHeadingComparisons([]);
      setFileMeta({ filename: result.filename, method: result.method, warnings: result.warnings || [] });
      setSource(result.source_text || '');
      setChanges([]);
      setReviewed(false);
    } catch (cause) {
      if (uploadVersion === fileSelectionVersion.current) setError(cause.message);
    } finally {
      if (uploadVersion === fileSelectionVersion.current) setBusy('');
    }
  }

  function changeEnhanceInput(setter, value) {
    // Resume facts and the intent of the requested rewrite both bind the
    // response. A reply based on an earlier intent must not be accepted.
    editVersion.current += 1;
    setter(value);
    setPendingAi(null);
  }

  function changeProvider(next) {
    if (next === provider) return;
    // A credential and privacy consent belong to exactly one provider.
    // Also invalidate any in-flight reply from the previous provider.
    editVersion.current += 1;
    setProvider(next);
    setApiKey('');
    setAiConsent(false);
    setPendingAi(null);
    setReviewed(false);
  }

  function loadDemo() {
    fileSelectionVersion.current += 1;
    editVersion.current += 1;
    setBusy('');
    setPendingAi(null);
    setError('');
    setDocumentToken((version) => version + 1);
    setResume(structuredClone(DEMO));
    setHandoffAdvice([]);
    setHandoffHeadingComparisons([]);
    setFileMeta({ filename: '演示简历（虚构数据）', method: 'demo', warnings: ['演示简历只用于功能体验，不含真实个人信息。'] });
    setSource('陈晓明\n后端开发工程师\n工作经历\n2022.07 - 2025.06 星辰科技\n项目经历\n订单分析平台');
    setReviewed(false);
    setChanges([]);
  }

  async function enhance() {
    if (!resume || busy) return;
    if (mode === 'ai' && !aiConsent) {
      setError('使用外部 AI 前，请在 AI 设置中确认隐私授权。');
      setSettingsOpen(true);
      return;
    }
    const requestVersion = editVersion.current;
    setPendingAi(null);
    setBusy('enhance'); setError('');
    try {
      const result = await requestJson('/api/enhance', {
        resume, use_ai: mode === 'ai', provider,
        api_key: mode === 'ai' ? apiKey : undefined,
        target_role: targetRole, job_description: jobDescription,
      });
      if (requestVersion !== editVersion.current) {
        setError('收到旧版本的润色结果，但你已经编辑了简历；为保护最新修改，本次结果已丢弃。');
        return;
      }
      if (result.mode === 'ai' && result.changes?.length) {
        setPendingAi({ changes: result.changes, selected: {}, version: requestVersion });
        setChanges([]);
      } else {
        editVersion.current += 1;
        setResume(result.resume);
        setChanges(result.changes || []);
      }
      setReviewed(false);
      setFileMeta((previous) => ({ ...previous, warnings: [...(previous?.warnings || []), ...(result.warnings || [])] }));
    } catch (cause) {
      setError(cause.message);
    } finally {
      setBusy('');
    }
  }

  function applyApprovedChanges() {
    if (!pendingAi) return;
    if (pendingAi.version !== editVersion.current) {
      setError('建议已过期，请重新润色。');
      setPendingAi(null);
      return;
    }
    const approved = pendingAi.changes.filter((_, i) => pendingAi.selected[i]);
    const updated = structuredClone(resume);
    for (const item of approved) {
      const validPath = /^(summary|(?:experience|projects)\.\d+\.bullets\.\d+)$/.test(item.field);
      if (!validPath || typeof item.after !== 'string' || typeof item.before !== 'string') {
        setError('润色结果包含无效字段，已拒绝应用。');
        return;
      }
      const keys = item.field.split('.');
      let parent = updated;
      for (const key of keys.slice(0, -1)) parent = parent?.[key];
      const last = keys[keys.length - 1];
      if (!parent || parent[last] !== item.before) {
        setError('润色对应的原始内容已变化，已拒绝应用。');
        return;
      }
      parent[last] = item.after;
    }
    editVersion.current += 1;
    setResume(updated);
    setChanges(approved);
    setPendingAi(null);
    setReviewed(false);
  }

  async function exportAs(format) {
    if (!resume || !reviewed || pendingAi || busy) return;
    setBusy(format); setError('');
    try {
      const response = await fetch('/api/export?format=' + format, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resume }),
      });
      if (!response.ok) {
        const message = await response.json().catch(() => ({}));
        throw new Error(message.detail || '文件导出失败');
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = 'paperpro_resume.' + format;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    } catch (cause) {
      setError(cause.message);
    } finally {
      setBusy('');
    }
  }

  const workflowStep = !resume ? 0 : reviewed ? 2 : 1;

  return (
    <div className="app">
      <Header config={config} onSettings={() => setSettingsOpen(true)}/>
      <main className="main-container">
        <div className="hero">
          <div>
            <div className="eyebrow"><IconSparkles size={14}/> YOUR NEXT CHAPTER STARTS HERE</div>
            <h1>让经历清晰，让机会<span>看见你。</span></h1>
            <p>从散乱的 PDF、Word 或扫描件，到专业、统一、可编辑的简历。</p>
          </div>
          <div className="hero-decoration" aria-hidden="true">
            <div className="hero-decoration-card one"/>
            <div className="hero-decoration-card two"/>
            <div className="hero-decoration-spark">✦</div>
          </div>
        </div>

        <WorkflowSteps state={workflowStep}/>
        {error && <Alert className="global-error" icon={<IconAlertTriangle size={18}/>} color="red" withCloseButton onClose={() => setError('')} title="操作未完成">{error}</Alert>}

        <div className="studio-grid">
          <div className="studio-left">
            <Paper className="workspace-card" radius="xl" p="lg">
              <Group justify="space-between" align="flex-start" mb="md">
                <div>
                  <div className="section-kicker">STEP 01 / INPUT</div>
                  <Title order={3} className="panel-title">导入你的简历</Title>
                  <Text c="dimmed" size="sm" mt={4}>支持多种格式，自动读取文本与扫描内容</Text>
                </div>
                <ThemeIcon variant="light" color="indigo" size={38} radius="md"><IconFileUpload size={20}/></ThemeIcon>
              </Group>

              {!fileMeta ? (
                <Dropzone className="upload-zone" maxSize={12 * 1024 * 1024} accept={ACCEPT}
                  maxFiles={1} onDrop={(files) => uploadFile(files[0])}
                  onReject={() => setError('请选择有效的 PDF、Word 或图片文件，大小不超过 12 MB。')}
                  disabled={!!busy}
                  data-testid="file-dropzone">
                  <Stack gap={8} align="center">
                    <div className="upload-art"><IconCloudUpload size={32} stroke={1.6}/></div>
                    <Text fw={700} className="upload-title">拖拽文件到这里，或点击选择</Text>
                    <Text size="sm" c="dimmed">支持 PDF · DOC / DOCX · PNG / JPG</Text>
                    <Group gap={7} mt={3} className="format-pills">
                      <span><IconFileTypePdf size={15}/> PDF</span>
                      <span><IconFileTypeDocx size={15}/> Word</span>
                      <span><IconFileTypePng size={15}/> 扫描图片</span>
                    </Group>
                    {busy === 'extract' && <Group mt="sm"><Loader size="xs"/><Text size="sm">正在识别文件...</Text></Group>}
                  </Stack>
                </Dropzone>
              ) : (
                <div className="uploaded-file">
                  <ThemeIcon size={42} variant="light" radius="md"><IconFileDescription size={23}/></ThemeIcon>
                  <div className="file-info">
                    <Text fw={700} size="sm" lineClamp={1}>{fileMeta.filename}</Text>
                    <Group gap={5} mt={2}><IconCircleCheck size={14} color="#179b72"/><Text size="xs" c="dimmed">已完成解析 · {fileMeta.method}</Text></Group>
                  </div>
                  <FileButton onChange={uploadFile} accept={FORMATS}>
                    {(props) => <Button {...props} variant="light" size="xs" leftSection={<IconRefresh size={14}/>} disabled={!!busy}>替换</Button>}
                  </FileButton>
                </div>
              )}
              {!resume && <Button fullWidth variant="subtle" size="sm" mt="sm" onClick={loadDemo} data-testid="demo-button">或先使用演示简历体验工作台 <IconArrowRight size={15} style={{ marginLeft: 5 }}/></Button>}
              {fileMeta?.warnings?.length > 0 && <div className="warnings-box">
                {fileMeta.warnings.slice(-3).map((warning, i) => <Group gap={7} align="start" key={i} wrap="nowrap">
                  <IconInfoCircle size={15} className="warning-icon"/>
                  <Text size="xs">{warning}</Text>
                </Group>)}
              </div>}
            </Paper>

            {handoffAdvice.length > 0 && <Paper className="workspace-card" radius="xl" p="lg"
              data-testid="handoff-advice">
              <Title order={3} className="panel-title">诊断中已选的优化建议</Title>
              <Text size="xs" c="dimmed" mt="xs" mb="sm">
                仅作为修改清单，不会自动添加事实、修改简历或代替最终审核。
              </Text>
              <Stack gap="xs">
                {handoffAdvice.map(item => <Paper p="sm" withBorder radius="md" key={item.id}>
                  <Text size="xs" c="dimmed">{item.id} · {item.location}</Text>
                  <Text size="sm" fw={650}>{item.title}</Text>
                  <Text size="sm">{item.action}</Text>
                </Paper>)}
              </Stack>
            </Paper>}

            {resume && <Paper key={documentToken} className="workspace-card" radius="xl" p="lg" data-testid="editor-panel">
              <Group justify="space-between" align="flex-start" mb="md">
                <div>
                  <div className="section-kicker">STEP 02 / EDIT</div>
                  <Title order={3} className="panel-title">核对与编辑</Title>
                  <Text c="dimmed" size="sm" mt={4}>所有修改实时同步到右侧预览</Text>
                </div>
                <Badge variant="light" color="indigo" size="lg">可编辑</Badge>
              </Group>

              <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
                <TextInput label="姓名" required value={resume.name} onChange={(e) => updateField('name', e.currentTarget.value)} data-testid="field-name"/>
                <TextInput label="求职方向 / 当前职位" value={resume.title} onChange={(e) => updateField('title', e.currentTarget.value)}/>
                <TextInput label="电子邮箱" value={resume.email} onChange={(e) => updateField('email', e.currentTarget.value)}/>
                <TextInput label="联系电话" value={resume.phone} onChange={(e) => updateField('phone', e.currentTarget.value)}/>
                <TextInput label="城市 / 地区" value={resume.location} onChange={(e) => updateField('location', e.currentTarget.value)}/>
                <DelimitedField label="个人链接（用逗号分开）" delimiter="commas" values={resume.links}
                  onChange={(items) => updateField('links', items)}/>
              </SimpleGrid>
              <SectionLabel>个人简介</SectionLabel>
              <Textarea autosize minRows={3} maxRows={7} value={resume.summary}
                onChange={(e) => updateField('summary', e.currentTarget.value)} placeholder="用简洁、真实的语言突出你的经历和专长"/>
              <SectionLabel>专业技能</SectionLabel>
              <DelimitedField label="专业技能" multiline delimiter="commas" autosize minRows={2} maxRows={5}
                data-testid="field-skills" values={resume.skills}
                onChange={(items) => updateField('skills', items)}
                description="使用逗号分隔不同技能"/>

              <Accordion className="edit-accordion" variant="separated" multiple defaultValue={['experience']} mt="md">
                <Accordion.Item value="experience">
                  <Accordion.Control><Text fw={650} size="sm">工作 / 实习经历</Text></Accordion.Control>
                  <Accordion.Panel><EntryEditor title="工作经历" entries={resume.experience} onChange={(i,f,v) => updateEntry('experience',i,f,v)}
                    headingComparisons={handoffHeadingComparisons}
                    onAdd={() => addEntry('experience')} onRemove={(i) => removeEntry('experience',i)}/></Accordion.Panel>
                </Accordion.Item>
                <Accordion.Item value="projects">
                  <Accordion.Control><Text fw={650} size="sm">项目经历</Text></Accordion.Control>
                  <Accordion.Panel><EntryEditor title="项目经历" entries={resume.projects} onChange={(i,f,v) => updateEntry('projects',i,f,v)}
                    onAdd={() => addEntry('projects')} onRemove={(i) => removeEntry('projects',i)}/></Accordion.Panel>
                </Accordion.Item>
                <Accordion.Item value="education">
                  <Accordion.Control><Text fw={650} size="sm">教育背景</Text></Accordion.Control>
                  <Accordion.Panel><EntryEditor title="教育背景" entries={resume.education} kind="education" onChange={(i,f,v) => updateEntry('education',i,f,v)}
                    onAdd={() => addEntry('education')} onRemove={(i) => removeEntry('education',i)}/></Accordion.Panel>
                </Accordion.Item>
                <Accordion.Item value="additional">
                  <Accordion.Control><Text fw={650} size="sm">其他信息 / 未分类内容</Text></Accordion.Control>
                  <Accordion.Panel>
                    <DelimitedField autosize minRows={3} maxRows={9} description="识别不明确的内容保留在这里，不会自动删除"
                      values={resume.additional} onChange={(items) => updateField('additional', items)}/>
                  </Accordion.Panel>
                </Accordion.Item>
              </Accordion>
            </Paper>}

            {resume && <Paper className="workspace-card" radius="xl" p="lg">
              <Group justify="space-between" align="flex-start" mb="sm">
                <div>
                  <div className="section-kicker">STEP 02 / ENHANCE</div>
                  <Title order={3} className="panel-title">专业表达优化</Title>
                </div>
                <ThemeIcon size={38} variant="light" color="indigo" radius="md"><IconWand size={20}/></ThemeIcon>
              </Group>
              <SegmentedControl fullWidth color="indigo" value={mode}
                onChange={(next) => changeEnhanceInput(setMode, next)}
                data={[{ label: '本地安全整理', value: 'local' }, { label: 'AI 智能润色', value: 'ai' }]}/>
              <Text size="xs" c="dimmed" mt="xs">
                {mode === 'local' ? '不联网、不添加新事实，仅整理格式与行文。' : '经授权将简历内容发送给你配置的 AI 服务，输出仍须审核。'}
              </Text>
              <TextInput mt="md" label="目标岗位（可选）" placeholder="例如：后端开发 / 产品经理"
                value={targetRole} onChange={(e) => changeEnhanceInput(setTargetRole, e.currentTarget.value)}/>
              <Textarea mt="sm" autosize minRows={2} maxRows={5} label="岗位描述（可选）"
                description="在本地模式中仅供查看与编辑；只有切换 AI 并主动授权后才可能发送给所选服务商。"
                placeholder="粘贴 JD 帮助理解岗位；不会自动补写未核实的经历。"
                value={jobDescription} onChange={(e) => changeEnhanceInput(setJobDescription, e.currentTarget.value)}/>
              {mode === 'ai' && <>
                <Text size="sm" fw={700} mt="md" mb={6}>AI 服务商</Text>
                <SegmentedControl fullWidth color="indigo" value={provider} onChange={changeProvider}
                  data-testid="ai-provider"
                  data={[{ label: 'DeepSeek', value: 'deepseek' }, { label: '自定义 API', value: 'configured' }]}/>
                <Text size="xs" c="dimmed" mt={6}>
                  {provider === 'deepseek'
                    ? '调用 DeepSeek 官方 deepseek-flash 模型。需使用 DeepSeek API Key。'
                    : '使用本地环境变量配置的 OpenAI 兼容 API 与对应密钥。'}
                </Text>
                {!aiConsent && <Alert mt="sm" color="orange" variant="light" icon={<IconLock size={16}/>}>使用前请先在 AI 设置中同意发送数据。<Button variant="transparent" size="compact-xs" onClick={() => setSettingsOpen(true)}>打开设置</Button></Alert>}
              </>}
              <Button mt="md" fullWidth leftSection={<IconSparkles size={18}/>} onClick={enhance}
                loading={busy === 'enhance'} disabled={!!busy && busy !== 'enhance'} data-testid="enhance-button">
                {mode === 'ai' ? '使用 AI 优化文字' : '整理表达与格式'}
              </Button>
              {pendingAi && <div className="changes-list" data-testid="changes-list">
                <Text fw={700} size="sm" mb={6}>AI 改写建议（尚未应用）：{pendingAi.changes.length} 处</Text>
                <Text size="xs" c="orange" mb={8}>
                  AI 可能新增不真实的描述。对照原文逐项核对后，勾选你确认真实的修改。
                </Text>
                {pendingAi.changes.map((change, i) => <div key={i} className="change-item">
                  <Text size="xs" fw={700} c="indigo" mb={5}>{change.field}</Text>
                  <Text size="xs" c="dimmed">原文：{change.before}</Text>
                  {(change.review_flags||[]).map((note,index)=><Text key={index} size="xs" c="orange"
                    data-testid="ai-review-warning">需核对：{note}</Text>)}
                  <Checkbox mt={8} checked={!!pendingAi.selected[i]}
                    onChange={(e) => {
                      const checked = e.currentTarget.checked;
                      setPendingAi((previous) => previous && ({
                        ...previous, selected: { ...previous.selected, [i]: checked },
                      }));
                    }}
                    label={<Text size="xs" fw={600}>{change.after}</Text>}/>
                </div>)}
                <Group mt="md" gap="xs">
                  <Button size="sm" onClick={applyApprovedChanges}
                    disabled={!Object.values(pendingAi.selected).some(Boolean)}>
                    应用已批准的修改
                  </Button>
                  <Button size="sm" variant="subtle" color="gray"
                    onClick={() => setPendingAi(null)}>放弃全部建议</Button>
                </Group>
              </div>}
              {!pendingAi && changes.length > 0 && <div className="changes-list" data-testid="changes-list">
                <Text fw={700} size="sm" mb={7}>已应用调整：{changes.length} 处</Text>
                {changes.map((change, i) => <div key={i} className="change-item">
                  <Text size="xs" fw={700} c="indigo">{change.field}</Text>
                  <Text size="xs" c="dimmed">修改前：<s>{change.before}</s></Text>
                  <Text size="xs">修改后：{change.after}</Text>
                </div>)}
              </div>}
            </Paper>}

            {resume && <Paper className="workspace-card" radius="xl" p="lg" data-testid="export-panel">
              <div className="section-kicker">STEP 03 / EXPORT</div>
              <Title order={3} className="panel-title">最后一步：审核并导出</Title>
              <Text c="dimmed" size="sm" mt={4}>使用固定的 PaperPro Classic A4 模板</Text>
              {!resume.name?.trim()&&<Alert color="blue" variant="light" mt="sm">
                姓名尚未填写；可以先导出简历草稿，正式投递前再补充。
              </Alert>}
              <div className="review-consent">
                <Checkbox checked={reviewed} disabled={!!pendingAi}
                  onChange={(e) => setReviewed(e.currentTarget.checked)}
                  label="我已核对当前填写的信息和所采纳的改写建议（空缺项可以稍后补充）"
                  data-testid="review-checkbox"/>
              </div>
              <SimpleGrid cols={2} spacing="sm" mt="md">
                <Button variant="light" leftSection={<IconFileTypeDocx size={19}/>}
                  onClick={() => exportAs('docx')} disabled={!reviewed || !!pendingAi || !!busy} loading={busy === 'docx'}
                  data-testid="download-docx">Word 文档</Button>
                <Button leftSection={<IconFileTypePdf size={19}/>}
                  onClick={() => exportAs('pdf')} disabled={!reviewed || !!pendingAi || !!busy} loading={busy === 'pdf'}
                  data-testid="download-pdf">PDF 文件</Button>
              </SimpleGrid>
              {!reviewed && <Text size="xs" c="dimmed" mt="sm" ta="center">勾选事实审核后解锁两个导出按钮</Text>}
            </Paper>}
          </div>

          <div className="studio-right">
            <div className="preview-sticky">
              <div className="preview-toolbar">
                <div>
                  <div className="section-kicker">LIVE PREVIEW</div>
                  <Title order={3} className="panel-title">简历预览 <span className="preview-live-dot"/></Title>
                </div>
                <Group gap="xs"><Badge variant="outline" color="gray">A4</Badge><Badge variant="light" color="indigo">Classic · 01</Badge></Group>
              </div>
              <div className="preview-canvas"><ResumePreview resume={resume}/></div>
              <div className="preview-hint"><IconShieldCheck size={16}/> 排版示意 · 实际文档由统一模板生成</div>
              {source && <details className="source-details" data-testid="source-details">
                <summary><IconFileDescription size={16}/> 查看原始识别文本 <span>校对依据</span></summary>
                <ScrollArea.Autosize mah={270}><pre className="source-text">{source}</pre></ScrollArea.Autosize>
              </details>}
            </div>
          </div>
        </div>
        <footer className="footer">
          <div className="brand-name">paper<span>pro</span></div>
          <Text size="xs" c="dimmed">本地简历工作台 · 无数据库 · 默认不上传云端 · 所有 AI 改写需人工核实</Text>
        </footer>
      </main>

      <Modal opened={settingsOpen} onClose={() => setSettingsOpen(false)} title={<Text fw={700}>AI 服务与隐私设置</Text>} centered size="md" radius="lg">
        <Stack gap="sm">
          <Alert icon={<IconShieldCheck size={17}/>} color="blue" variant="light">
            默认仅在本机处理文件。只有选择 AI 润色并明确授权时，才会将简历文字发送给外部 AI 服务。
          </Alert>
          <TextInput label="API Key（仅在当前页面内存中）" type="password" autoComplete="off"
            placeholder={(provider === 'deepseek' ? config?.deepseek_ai_available : config?.ai_available)
              ? '当前服务商已配置服务器密钥，可留空'
              : provider === 'deepseek' ? '输入 DeepSeek API Key' : '输入自定义服务的 API Key'}
            value={apiKey} onChange={(e) => changeEnhanceInput(setApiKey, e.currentTarget.value)}/>
          <Text size="xs" c="dimmed">
            固定配置请编辑项目根目录的 settings.json；实际密钥建议填写在 Git 忽略的 settings.local.json 中，刷新页面可更新配置状态。DeepSeek 与自定义 API 的密钥互相隔离。
          </Text>
          <Checkbox checked={aiConsent} onChange={(e) => changeEnhanceInput(setAiConsent, e.currentTarget.checked)}
            label="我同意仅在主动点击 AI 优化时将本次简历内容发送给所配置的服务。"/>
          <Button fullWidth onClick={() => setSettingsOpen(false)}>保存本次会话设置</Button>
        </Stack>
      </Modal>
    </div>
  );
}
