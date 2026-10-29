import { useEffect, useRef, useState } from 'react';
import {
  Accordion, Alert, Badge, Button, Checkbox, Divider, FileButton, Grid,
  Group, Loader, Paper, ScrollArea, SimpleGrid, Stack, Text, Textarea,
  TextInput, Title,
} from '@mantine/core';
import { Dropzone } from '@mantine/dropzone';
import {
  IconArrowLeft, IconArrowRight, IconChartBar, IconCircleCheck,
  IconClipboardCheck, IconCloudUpload, IconDownload, IconFileText,
  IconInfoCircle, IconLock, IconPlus, IconRefresh, IconSettings,
  IconShieldCheck, IconSparkles, IconTargetArrow, IconTrash,
} from '@tabler/icons-react';
import { createClassicHandoff, saveClassicHandoff } from './resumeHandoff.js';

const STEPS = ['上传简历', '校对信息', '目标职位', '诊断报告', '优化清单'];
const SECTIONS = [
  ['match','岗位匹配度量化'],
  ['experience','工作经验研判'],
  ['potential','学习能力与发展潜力'],
  ['motivation','岗位重视度'],
  ['verification','简历智能验真'],
];
const JOBS = ['后端开发工程师', '前端开发工程师', 'Java 开发工程师', '数据分析师',
  '算法工程师', '机器学习工程师', '产品经理', 'UX 设计师', '测试工程师',
  '软件工程师', '项目经理', '运营专员'];
const ACCEPT = {
  'application/pdf': ['.pdf'],
  'application/msword': ['.doc'],
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
  'image/png': ['.png'],
  'image/jpeg': ['.jpg', '.jpeg'],
};
const KEYS = {
  name:'姓名',title:'当前职位 / 求职方向',email:'电子邮箱',phone:'电话',location:'所在城市',
  summary:'个人简介',self_evaluation:'自我评价',
};

const DEMO = [
  '陈晓明',
  '求职意向：后端开发工程师',
  '联系方式 demo@example.com',
  '个人简介',
  '拥有3年后端系统开发经验，熟悉 Python 与 SQL。',
  '专业技能',
  'Python, SQL, Docker, Git',
  '工作经历',
  '2022.07 - 2025.06 星辰科技 | 后端开发工程师',
  '- 参与订单系统后端开发，使用 Python 和 SQL。',
  '- 优化接口响应时间20%。',
  '项目经历',
  '订单服务系统',
  '- 开发 Python API，维护 Docker 部署。',
  '教育背景',
  '2018.09 - 2022.06 本科计算机科学',
  '证书',
  'CET-6',
].join('\n');

async function api(path, json) {
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(json),
  });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof body.detail === 'string' ? body.detail : '请求失败，请核对输入');
  return body;
}
function lines(text) {
  return text.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
}
function joinLines(values) { return (values || []).join('\n'); }
function Status({ text, color = 'blue' }) { return <Badge color={color} radius="sm" variant="light">{text}</Badge>; }
function StepTitle({ code, title, children }) {
  return <div className="diag-step-heading">
    <div className="diag-eyebrow">{code} / PAPERPRO WORKSPACE</div>
    <Title order={2}>{title}</Title>
    <Text size="sm" c="dimmed" mt={7}>{children}</Text>
  </div>;
}
function Panel({ title, children, extra, testId }) {
  return <Paper className="diag-panel" p="xl" radius="lg" data-testid={testId}>
    <Group justify="space-between" align="center" mb="lg" wrap="wrap">
      <Title order={3} className="diag-panel-title">{title}</Title>
      {extra}
    </Group>
    {children}
  </Paper>;
}
function Evidence({ refs }) {
  if (!refs?.length) return <Text size="xs" c="dimmed">简历中未找到直接文字证据；不代表实际能力缺失。</Text>;
  return <div className="diag-evidence">
    {refs.map((ref, i) => <div key={i}><code>{ref.path}</code><span>{ref.original}</span></div>)}
  </div>;
}
function Match({ data }) {
  return <>
    <div className="diag-score-intro">
      <div className="diag-score-ring" style={{ '--score': data.score || 0 }}>
        <span>{data.score}</span><small>/ 100</small>
      </div>
      <div className="diag-score-copy">
        <Group gap="xs" wrap="wrap"><Status text={'匹配等级 · ' + data.grade} color={data.grade === '高' ? 'teal' : data.grade === '中' ? 'blue' : 'orange'}/>
        <Status text={'置信说明 · ' + data.confidence} color="gray"/></Group>
        <Title order={3} mt="sm">{data.score_kind || '岗位证据覆盖度'}</Title>
        <Text size="sm" c="dimmed">{data.conclusion}</Text>
        <Text size="xs" mt={7}>{data.hr_interpretation}</Text>
        {data.job_fit_applicable===false&&<Text size="xs" c="orange" mt={4}>此数字不可与明确岗位的匹配分数横向比较。</Text>}
      </div>
    </div>
    <Alert variant="light" color="blue" icon={<IconInfoCircle size={17}/>} mb="md">
      {data.calibration_warning}
    </Alert>
    <div className="diag-table-wrap">
      <table className="diag-table" data-testid="requirements-table">
        <thead><tr><th>关键要求</th><th>匹配状态</th><th>系数</th><th>有效权重</th><th>原文证据</th></tr></thead>
        <tbody>{data.requirements.map(item => <tr key={item.id}>
          <td><strong>{item.label}</strong><Text size="xs" c="dimmed">{item.reason}</Text></td>
          <td><Status text={item.status} color={item.status === '已体现' ? 'teal' : item.status === '简历未体现' ? 'orange' : 'gray'}/></td>
          <td>{(item.coefficient * 100).toFixed(0)}%</td>
          <td>{(item.effective_weight * 100).toFixed(1)}%</td>
          <td><Evidence refs={item.evidence_refs}/></td>
        </tr>)}</tbody>
      </table>
    </div>
  </>;
}
function Experience({ data }) {
  return <>
    <Group gap="sm" mb="md">
      <div className="diag-mini-stat"><strong>{data.stability_score == null ? '未知' : data.stability_score}</strong><small>稳定性参考分</small></div>
      <div className="diag-mini-stat"><strong>{data.months_total}</strong><small>已记录任职月数（去重）</small></div>
      <div className="diag-mini-stat"><strong>{data.gaps?.length || 0}</strong><small>需说明的空档</small></div>
    </Group>
    <Text size="sm">{data.career_continuity}</Text>
    <Text size="sm">{data.career_progression}</Text>
    <Divider my="md"/>
    <Text fw={700} size="sm" mb="xs">关键时间节点</Text>
    {(data.timeline || []).length ? data.timeline.map((node, i) => <div key={i} className="diag-timeline">
      <span>{node.start.slice(0, 7)} — {node.end.slice(0, 7)}</span>
      <div><strong>{node.company || '未填写公司'}</strong> · {node.role || '未填写职位'} <Text size="xs" c="dimmed">{node.months} 个月 · {node.path}</Text></div>
    </div>) : <Text size="sm" c="dimmed">没有可靠的起止年月，无法计算任期；请返回校对信息补齐。</Text>}
    <Text size="xs" c="dimmed" mt="md">{data.interpretation_boundary}</Text>
  </>;
}
function Potential({ data }) {
  return <>
    <Group mb="md" gap="sm"><Status text={'证据信号评级 · ' + data.rating} color="indigo"/>
      <Text size="sm">{data.conclusion}</Text></Group>
    <div className="diag-signal-grid">{(data.signals || []).map((s, i) => <div className="diag-signal" key={i}>
      <Group justify="space-between"><strong>{s.signal}</strong><Status text={s.status} color={s.status === '支持' ? 'teal' : 'gray'}/></Group>
      <Text size="xs" c="dimmed">{s.path}</Text>
      <Text size="sm">{s.original || '简历未体现——请按实际情况补充'}</Text>
    </div>)}</div>
    <Alert color="blue" variant="light" mt="md" title={'可补强：' + data.weakness.signal}>{data.weakness.action}</Alert>
    <Text size="xs" c="dimmed" mt="sm">{data.caveat}</Text>
  </>;
}
function Motivation({ data }) {
  return <>
    <Group mb="md"><Status text={'定制程度 · ' + data.rating}/><Text size="sm">{data.conclusion}</Text></Group>
    <Text size="sm" mb="sm">{data.rationale}</Text>
    <Evidence refs={data.evidence}/>
    <Alert color="blue" mt="lg" variant="light" title="改进方向">{data.suggestion}</Alert>
  </>;
}
function Verification({ data }) {
  return <>
    <Text size="sm" mb="md">{data.conclusion}</Text>
    {(data.issues || []).length ? data.issues.map((it, i) => <div className="diag-issue" key={it.id || i}>
      <Group mb="xs"><Status text={it.severity + ' · 需核对'} color={it.severity === '高' ? 'orange' : 'gray'}/><strong>{it.type}</strong></Group>
      <Text size="xs" c="dimmed">证据位置：{it.location}</Text>
      <Text size="sm">{it.original}</Text>
      {it.related_location&&<Paper p="sm" withBorder radius="sm" mt="xs"
        data-testid="verification-opposing-claim">
        <Text size="xs" c="dimmed">另一处描述：{it.related_location}</Text>
        <Text size="sm">{it.related_original}</Text>
      </Paper>}
      <Text size="sm" mt={6}>{it.reason}</Text>
    </div>) : <Alert color="teal" variant="light">暂未发现规则能识别的存疑点；这不代表简历信息已经被外部核实。</Alert>}
    <Text size="xs" c="dimmed" mt="sm">{data.caveat}</Text>
  </>;
}
const REPORT_COMPONENTS = {match:Match, experience:Experience,potential:Potential,motivation:Motivation,verification:Verification};

function ResumeEditor({ resume, update, updateExperience, updateEntry, addEntry, removeEntry }) {
  return <Stack gap="lg">
    <Panel title="基本信息与自我评价">
      <SimpleGrid cols={{base:1,sm:2}} spacing="sm">
        {['name','title','email','phone','location'].map(field =>
          <TextInput key={field} label={KEYS[field]} value={resume[field] || ''}
            onChange={e => update(field,e.currentTarget.value)} data-testid={'candidate-'+field}/>)}
      </SimpleGrid>
      <Textarea mt="md" minRows={3} autosize label="个人简介"
        value={resume.summary || ''} onChange={e => update('summary',e.currentTarget.value)}/>
      <Textarea mt="sm" minRows={2} autosize label="自我评价"
        value={resume.self_evaluation || ''} onChange={e => update('self_evaluation',e.currentTarget.value)}/>
    </Panel>
    <Panel title="技能与证书">
      <Textarea label="技能（每行一项）" autosize minRows={2} value={joinLines(resume.skills)}
        onChange={e => update('skills',lines(e.currentTarget.value))}/>
      <Textarea label="证书 / 资质（每行一项）" mt="md" autosize minRows={2}
        value={joinLines(resume.certificates)} onChange={e => update('certificates',lines(e.currentTarget.value))}/>
    </Panel>
    <Panel title="工作 / 实习经历" extra={<Button size="xs" variant="light" onClick={() => addEntry('experience')}
      leftSection={<IconPlus size={15}/>}>添加经历</Button>}>
      {(resume.experience || []).length === 0 && <Text size="sm" c="dimmed">尚无工作记录；可以添加实习经历，也可以留空。</Text>}
      {(resume.experience || []).map((entry, index) => <div className="diag-edit-entry" key={index}>
        <Group justify="space-between" mb="sm"><Text fw={700}>经历 {index+1}</Text>
          <Button size="xs" color="gray" variant="subtle" onClick={() => removeEntry('experience',index)} leftSection={<IconTrash size={13}/>}>删除</Button>
        </Group>
        <SimpleGrid cols={{base:1,sm:2}} spacing="sm">
          <TextInput label="公司 / 机构" value={entry.company||''} data-testid={'experience-company-'+index}
            onChange={e=>updateExperience(index,'company',e.currentTarget.value)}/>
          <TextInput label="职位 / 职能" value={entry.role||''} data-testid={'experience-role-'+index}
            onChange={e=>updateExperience(index,'role',e.currentTarget.value)}/>
          <TextInput label="开始年月" placeholder="2022.07" value={entry.start_date||''}
            data-testid={'experience-start-'+index} onChange={e=>updateExperience(index,'start_date',e.currentTarget.value)}/>
          <TextInput label="结束年月" placeholder="2025.06 或 至今" value={entry.end_date||''}
            data-testid={'experience-end-'+index} onChange={e=>updateExperience(index,'end_date',e.currentTarget.value)}/>
        </SimpleGrid>
        <TextInput label="原始经历标题（用于溯源）" mt="sm" value={entry.heading||''}
          onChange={e=>updateExperience(index,'heading',e.currentTarget.value)}/>
        <Textarea mt="sm" minRows={3} autosize label="具体职责与成果（每行一项）"
          value={joinLines(entry.bullets)} onChange={e=>updateExperience(index,'bullets',lines(e.currentTarget.value))}/>
      </div>)}
    </Panel>
    <Panel title="项目与教育背景">
      {['projects','education'].map(group => <div key={group} className="diag-edit-group">
        <Group justify="space-between" mb="sm"><Text fw={700}>{group==='projects'?'项目经历':'教育背景'}</Text>
          <Button size="xs" variant="light" leftSection={<IconPlus size={14}/>}
            onClick={()=>addEntry(group)}>添加</Button></Group>
        {(resume[group]||[]).map((entry,i) => <div className="diag-edit-entry" key={i}>
          <Group justify="space-between" mb="xs"><Text size="xs">条目 {i+1}</Text>
            <Button size="xs" color="gray" variant="subtle" onClick={()=>removeEntry(group,i)}>删除</Button></Group>
          <TextInput label={group==='projects'?'项目标题':'学校、学历与时间'} value={entry.heading||''}
            onChange={e=>updateEntry(group,i,'heading',e.currentTarget.value)}/>
          <Textarea mt="sm" autosize minRows={2} label={group==='projects'?'项目动作/成果':'教育补充信息'}
            value={joinLines(entry[group==='projects'?'bullets':'details'])}
            onChange={e=>updateEntry(group,i,group==='projects'?'bullets':'details',lines(e.currentTarget.value))}/>
        </div>)}
      </div>)}
    </Panel>
    <Panel title="其他未分类内容">
      <Textarea autosize minRows={2} value={joinLines(resume.additional)}
        onChange={e=>update('additional',lines(e.currentTarget.value))}/>
    </Panel>
  </Stack>;
}

export default function CandidateDiagnosisApp() {
  const [step,setStep]=useState(0);
  const [resume,setResume]=useState(null);
  const [fileMeta,setFileMeta]=useState(null);
  const [paste,setPaste]=useState('');
  const [target,setTarget]=useState({role:'',company:'',job_description:''});
  const [enabled,setEnabled]=useState(SECTIONS.map(x=>x[0]));
  const [aiEnabled,setAiEnabled]=useState(false);
  const [aiConsent,setAiConsent]=useState(false);
  const [aiKey,setAiKey]=useState("");
  const [report,setReport]=useState(null);
  const [selected,setSelected]=useState([]);
  const [selectedQuestions,setSelectedQuestions]=useState([]);
  const [reviewHints,setReviewHints]=useState([]);
  const [busy,setBusy]=useState('');
  const [elapsed,setElapsed]=useState(0);
  const [error,setError]=useState('');
  const [navNotice,setNavNotice]=useState('');
  const requestId=useRef(0);

  useEffect(()=>{
    if(!busy){setElapsed(0);return undefined;}
    const began=Date.now();
    const timer=setInterval(()=>setElapsed(Math.floor((Date.now()-began)/1000)),1000);
    return ()=>clearInterval(timer);
  },[busy]);

  function invalidate() {
    // The inputs bind an in-flight diagnosis: changing any input revokes the
    // older response, including the case where report generation is pending.
    requestId.current += 1;
    setBusy(previous => previous === 'report' ? '' : previous);
    setReport(null);setSelected([]);setSelectedQuestions([]);
    setNavNotice('信息已更新，原有报告已作废，需要重新生成。');
  }
  function modify(field,value){
    setResume(previous=>({...previous,[field]:value})); invalidate();
  }
  function modifyEntry(group,index,field,value){
    setResume(previous=>({...previous,[group]:previous[group].map((e,i)=>i===index?{...e,[field]:value}:e)}));
    if(group==='experience'){
      setReviewHints(previous=>previous.filter(h=>h.experience_index!==index));
    }
    invalidate();
  }
  function addEntry(group){
    const next=group==='experience'
      ? {heading:'',company:'',role:'',start_date:'',end_date:'',bullets:[]}
      : group==='education' ? {heading:'',details:[]} : {heading:'',bullets:[]};
    setResume(previous=>({...previous,[group]:[...previous[group],next]}));invalidate();
  }
  function removeEntry(group,index){
    setResume(previous=>({...previous,[group]:previous[group].filter((_,i)=>i!==index)}));
    if(group==='experience')setReviewHints([]);
    invalidate();
  }
  function acceptWorkHint(hint){
    const index=hint.experience_index;
    const entry=resume?.experience?.[index];
    if(!entry || entry.role || entry.heading!==hint.source_heading
       || !entry.company.includes(hint.suggested_company)
       || !entry.company.includes(hint.suggested_role)){
      setReviewHints(previous=>previous.filter(h=>h.id!==hint.id));
      return;
    }
    setResume(previous=>({
      ...previous,
      experience:previous.experience.map((item,i)=>i===index?{
        ...item,company:hint.suggested_company,role:hint.suggested_role
      }:item)
    }));
    setReviewHints(previous=>previous.filter(h=>h.id!==hint.id));
    invalidate();
  }
  function modifyTarget(field,value){setTarget(previous=>({...previous,[field]:value}));invalidate();}
  function changePaste(value){
    // Typing a new source invalidates a pending parse of the earlier text.
    requestId.current += 1;
    setPaste(value);
    setBusy(previous=>previous==='parse'?'':previous);
  }
  function receive(result){
    setResume(result.resume);
    setReviewHints(Array.isArray(result.review_hints)?
      result.review_hints.filter(h=>h.status==='unverified' && Number.isInteger(h.experience_index)) : []);
    setFileMeta({name:result.filename,method:result.method,sha256:result.sha256,warnings:result.warnings||[]});
    setReport(null);setSelected([]);setSelectedQuestions([]);setNavNotice('');
    setStep(1);
  }
  async function importFile(file){
    if(!file)return;
    const token=++requestId.current;
    setError('');
    if(file.size>10*1024*1024){setError('单文件上限 10 MB，请压缩后重新选择。');return;}
    const suffix=file.name.split('.').pop()?.toLowerCase();
    if(!['pdf','docx','doc','png','jpg','jpeg'].includes(suffix)){
      setError('仅支持 PDF、DOCX、DOC、PNG、JPG 或粘贴文本。');return;
    }
    const body=new FormData();body.append('file',file);
    setBusy('parse');
    try{
      const r=await fetch('/api/diagnosis/parse',{method:'POST',body});
      const data=await r.json().catch(()=>({}));
      if(!r.ok)throw new Error(data.detail||'解析失败，请核对文件格式');
      if(token!==requestId.current)return;
      receive(data);
    }catch(e){if(token===requestId.current)setError(e.message);}
    finally{if(token===requestId.current)setBusy('');}
  }
  async function importText(){
    if(!paste.trim())return;
    const token=++requestId.current;
    setBusy('parse');setError('');
    try{const data=await api('/api/diagnosis/paste',{text:paste});
      if(token!==requestId.current)return;
      receive(data);
    }catch(e){if(token===requestId.current)setError(e.message);}
    finally{if(token===requestId.current)setBusy('');}
  }
  async function generate(){
    if(!resume||(!target.role.trim()&&!target.company.trim())||busy)return;
    const token=++requestId.current;
    setBusy('report');setError('');setNavNotice('');
    try{
      const result=await api('/api/diagnosis/report',{
        resume,target,enabled_sections:enabled,
        use_ai:aiEnabled,ai_consent:aiEnabled&&aiConsent,
        ai_provider:'deepseek',api_key:aiEnabled?aiKey:undefined,
      });
      if(token!==requestId.current)return;
      setReport(result);setSelected([]);setSelectedQuestions([]);
      setStep(3);
    }catch(e){if(token===requestId.current)setError(e.message);}
    finally{if(token===requestId.current)setBusy('');}
  }
  async function exportSelected(kind,format){
    const choices=kind==='todo'?selected:selectedQuestions;
    if(!choices.length)return;
    setBusy('export');setError('');
    try{
      const response=await fetch('/api/diagnosis/export',{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({report,selected_ids:choices,kind,format}),
      });
      if(!response.ok){const info=await response.json().catch(()=>({}));
        throw new Error(info.detail||'清单导出失败');}
      const blob=await response.blob();
      const url=URL.createObjectURL(blob);
      const anchor=document.createElement('a');
      anchor.href=url;anchor.download='paperpro_'+(kind==='todo'?'todo':'interview_questions')+'.'+format;
      document.body.append(anchor);anchor.click();anchor.remove();
      setTimeout(()=>URL.revokeObjectURL(url),5000);
    }catch(e){setError(e.message);}
    finally{setBusy('');}
  }
  function openClassicWithReviewedDraft(){
    if(!resume || !report || busy)return;
    try{
      const handoff=createClassicHandoff(resume,target,report,selected,fileMeta);
      // Only an explicit user click saves these local browser-tab facts.
      // It does not approve suggestions or enable any external AI provider.
      saveClassicHandoff(window.sessionStorage,handoff);
      window.location.assign('/classic');
    }catch(e){setError(e.message||'简历交接失败，请重新尝试。');}
  }
  function goTo(newStep){
    if(newStep>step)return;
    if(newStep===3&&!report)return;
    if(newStep===4&&!report)return;
    if(busy==='report' && newStep<step){
      requestId.current += 1;
      setBusy('');
    }
    setError('');setStep(newStep);
  }
  function checkboxSetter(values,setter,id,checked){
    setter(checked?[...values,id]:values.filter(x=>x!==id));
  }
  const readyTarget=!!(target.role.trim()||target.company.trim());
  const questionList=report?.interview_questions||[];
  const suggestions=report?.suggestions||[];

  return <div className="diag-root" data-testid="candidate-app">
    <aside className="diag-sidebar">
      <div className="diag-logo"><div className="diag-mark">P</div><div><strong>paper<span>pro</span></strong><small>INTELLIGENT CAREER</small></div></div>
      <div className="diag-side-kicker">工作台 / WORKSPACE</div>
      <div className="diag-side-current"><IconChartBar size={18}/><span>简历增强诊断</span></div>
      <a className="diag-side-link" href="/classic"><IconFileText size={18}/>经典简历编辑</a>
      <div className="diag-side-bottom"><IconShieldCheck size={17}/><span>本地优先 · 原件不改写<br/>建议由你自主采纳</span></div>
    </aside>

    <div className="diag-shell">
      <header className="diag-topbar">
        <div><span>职业竞争力分析</span><small> / 求职者端</small></div>
        <Group gap="xs"><Status text="R7–R10 Beta" color="indigo"/><a className="diag-top-link" href="/classic"><IconSettings size={16}/>经典设置</a></Group>
      </header>
      <main className="diag-content">
        <div className="diag-hero">
          <div><div className="diag-eyebrow">CANDIDATE INTELLIGENCE / PERSONAL REPORT</div>
          <Title order={1}>不仅优化表述，更要看懂<span>过筛逻辑。</span></Title>
          <Text c="dimmed" mt="sm">五大 HR 视角诊断，把岗位差距、履历节点与可能被追问的证据，变成可执行的优化待办。</Text></div>
          <div className="diag-hero-art"><div className="diag-art-score">86<small>/100</small><div>Evidence-based insight</div></div><span className="diag-art-node a"/><span className="diag-art-node b"/></div>
        </div>

        <div className="diag-progress" data-testid="wizard-steps">
          {STEPS.map((s,i)=><button key={s} type="button" className={'diag-progress-item '+(i===step?'is-active':i<step?'is-done':'')}
            disabled={i>step||(i>=3&&!report)} onClick={()=>goTo(i)}>
            <span>{i<step?<IconCircleCheck size={17}/>:String(i+1).padStart(2,'0')}</span><strong>{s}</strong>
          </button>)}
        </div>
        {error&&<Alert mb="lg" color="red" withCloseButton onClose={()=>setError('')} title="操作未完成">{error}</Alert>}
        {navNotice&&<Alert mb="lg" color="orange" withCloseButton onClose={()=>setNavNotice('')}>{navNotice}</Alert>}
        {busy&&<Paper p="md" className="diag-loading" mb="lg">
          <Group gap="sm"><Loader size="sm"/><div><Text fw={700} size="sm">{busy==='parse'?'正在识别简历文字与结构':busy==='report'?'正在核算岗位要求与五维证据':'正在导出已勾选清单'}</Text>
          <Text size="xs" c="dimmed">{elapsed} 秒 · {elapsed>=10?'已超过 10 秒，仍在处理，请稍候；原文件不会更改。':'请稍候，结果生成后自动进入下一步。'}</Text></div></Group>
        </Paper>}

        {step===0&&<>
          <StepTitle code="01" title="上传简历，建立分析依据">支持文档、照片或粘贴文本。原件不改动；下一步由你核实解析内容。</StepTitle>
          <div className="diag-upload-grid">
            <Panel title="导入文件" extra={<Status text="单文件 ≤10 MB" color="gray"/>}>
              <Dropzone accept={ACCEPT} maxFiles={1} maxSize={10*1024*1024} disabled={!!busy}
                onDrop={files=>importFile(files[0])}
                onReject={()=>setError('文件无效：仅支持 PDF / Word / PNG / JPG，且不超过 10 MB。')}
                className="diag-dropzone" data-testid="candidate-dropzone">
                <IconCloudUpload size={40} stroke={1.5}/>
                <Text fw={750} mt="sm">拖拽简历或点击选择文件</Text>
                <Text c="dimmed" size="xs" mt={6}>PDF · DOCX · DOC · PNG · JPG</Text>
                <Text c="dimmed" size="xs" mt={3}>移动端可从相册或文件管理器选择</Text>
              </Dropzone>
              <Text c="dimmed" mt="md" size="xs">扫描文档会使用本地 OCR；复杂版式可能需要在下一步修正。</Text>
            </Panel>
            <Panel title="粘贴简历文本">
              <Textarea value={paste} onChange={e=>changePaste(e.currentTarget.value)}
                minRows={7} autosize placeholder="把简历全文粘贴在此，包含基本信息、教育、工作经历、技能等"
                data-testid="candidate-paste"/>
              <Group justify="space-between" mt="md">
                <Button variant="subtle" color="gray" size="sm" onClick={()=>setPaste(DEMO)}>填入虚构演示资料</Button>
                <Button onClick={importText} disabled={!paste.trim()||!!busy}
                  rightSection={<IconArrowRight size={16}/>} data-testid="candidate-parse-text">解析文本</Button>
              </Group>
            </Panel>
          </div>
        </>}

        {step===1&&resume&&<>
          <StepTitle code="02" title="核对并修正履历信息">先确认公司、职位、任职起止时间与技术项目；后续评分只使用你确认后的结构化文本。</StepTitle>
          <Panel title="来源与解析说明" extra={<Status text={'已导入 · '+fileMeta?.method} color="teal"/>}>
            <Group gap="sm" wrap="wrap"><Text size="sm" fw={650}>{fileMeta?.name}</Text>
              <Text size="xs" c="dimmed">原始 SHA-256：{fileMeta?.sha256?.slice(0,16)}…</Text></Group>
            {(fileMeta?.warnings||[]).map((w,i)=><Text size="xs" color="orange" key={i}>{w}</Text>)}
            <details className="diag-source"><summary>查看原始识别文本（核对依据）</summary>
              <pre>{resume.source_text||''}</pre></details>
          </Panel>
          {reviewHints.length>0&&<Panel title="待确认的工作职位排版提示"
            testId="candidate-work-hints" extra={<Status text={reviewHints.length+' 项待核对'} color="orange"/>}>
            <Alert color="orange" variant="light" mb="md" icon={<IconInfoCircle size={17}/>}>
              同行的文字块不一定构成真实职位。以下均为未经核实的候选项，
              默认不写入简历、不进入评分。请对照原 PDF 确认后再采纳。
            </Alert>
            {reviewHints.map(h=><Paper key={h.id} p="md" mb="sm" withBorder radius="md"
              data-testid={'work-hint-'+h.id}>
              <Group gap="xs" wrap="wrap">
                <Status text="低置信度 · 未经校准" color="gray"/>
                <Status text="等待人工核实" color="orange"/>
              </Group>
              <Text size="xs" c="dimmed" mt={8}>
                原文位置：{h.source_path}
                {h.evidence?.page_number ? ' · PDF 第 '+h.evidence.page_number+' 页' : ''}
              </Text>
              {h.evidence?.boxes?.role&&<Text size="xs" c="dimmed">
                职位文字块定位：横向 {Math.round(h.evidence.boxes.role[0]*100)}%–{Math.round(h.evidence.boxes.role[2]*100)}%，
                纵向 {Math.round(h.evidence.boxes.role[1]*100)}%–{Math.round(h.evidence.boxes.role[3]*100)}%
              </Text>}
              <Text size="sm" mt={5}>原文：{h.source_heading}</Text>
              <Text size="sm" fw={600} mt={5}>候选机构：{h.suggested_company}</Text>
              <Text size="sm" fw={600}>候选职位：{h.suggested_role}</Text>
              <Text size="xs" c="dimmed">同行排版属于弱证据，未经过语义核查；不表示真实任职或评分概率。</Text>
              <Group mt="sm" gap="xs">
                <Button size="xs" onClick={()=>acceptWorkHint(h)}
                  data-testid={'accept-'+h.id}>已核对，采纳到表单</Button>
                <Button size="xs" variant="subtle" color="gray"
                  onClick={()=>setReviewHints(previous=>previous.filter(x=>x.id!==h.id))}
                  data-testid={'ignore-'+h.id}>忽略此候选</Button>
              </Group>
            </Paper>)}
          </Panel>}
          <ResumeEditor resume={resume} update={modify} updateExperience={(i,f,v)=>modifyEntry('experience',i,f,v)}
            updateEntry={modifyEntry} addEntry={addEntry} removeEntry={removeEntry}/>
          <Group justify="space-between" mt="xl">
            <Button variant="subtle" leftSection={<IconArrowLeft size={16}/>} onClick={()=>setStep(0)}>返回更换文件</Button>
            <Button rightSection={<IconArrowRight size={16}/>} onClick={()=>setStep(2)} data-testid="candidate-next-target">下一步 · 设置目标</Button>
          </Group>
        </>}

        {step===2&&resume&&<>
          <StepTitle code="03" title="确定你的目标职位与公司">两者至少填写一项。粘贴真实岗位 JD 会让能力对照更有针对性；未提供 JD 时使用通用岗位假设并降低置信说明。</StepTitle>
          <Panel title="岗位定位">
            <SimpleGrid cols={{base:1,sm:2}}>
              <TextInput label="目标职位" placeholder="例如：后端开发工程师" value={target.role}
                onChange={e=>modifyTarget('role',e.currentTarget.value)}
                list="paperpro-job-suggestions" data-testid="candidate-target-role"/>
              <TextInput label="目标公司" placeholder="例如：示例科技有限公司" value={target.company}
                onChange={e=>modifyTarget('company',e.currentTarget.value)} data-testid="candidate-target-company"/>
            </SimpleGrid>
            <datalist id="paperpro-job-suggestions">{JOBS.map(item=><option value={item} key={item}/>)}</datalist>
            <Textarea mt="lg" minRows={6} autosize label="目标岗位 JD（可选，但推荐）"
              placeholder="请粘贴真实 JD：职责、任职条件、技术栈、工作年限等。我们不会根据公司名称虚构官方要求。"
              value={target.job_description} onChange={e=>modifyTarget('job_description',e.currentTarget.value)}/>
            {!readyTarget&&<Text size="xs" c="orange" mt="xs">至少填写目标职位或目标公司，才能生成报告。</Text>}
          </Panel>
          <Panel title="HR 视角诊断维度" extra={<Status text="可独立关闭" color="gray"/>}>
            <SimpleGrid cols={{base:1,sm:2}} spacing="lg">
              {SECTIONS.map(([id,name])=><Checkbox key={id} label={name} checked={enabled.includes(id)}
                onChange={e=>{
                  const checked=e.currentTarget.checked;
                  setEnabled(prev=>checked?[...new Set([...prev,id])]:prev.filter(x=>x!==id));
                  invalidate();
                }}/>)}
            </SimpleGrid>
            <Alert variant="light" color="blue" mt="lg" icon={<IconInfoCircle size={17}/>}>
              匹配度是“简历证据覆盖度”，不是 HR 录取概率。心理测量与经济学多准则权重尚需真实标注样本检验；本报告会明确展示规则版本。
            </Alert>
          </Panel>
          <Panel title="可选：DeepSeek 解读职业路径" extra={<Status text="默认关闭，不外发"/>}>
            <Checkbox checked={aiEnabled} label="使用 DeepSeek 为已计算的时间线与证据提供辅助解释（不允许重新打分）"
              onChange={e=>{setAiEnabled(e.currentTarget.checked);invalidate();}}/>
            {aiEnabled&&<Stack gap="sm" mt="md">
              <TextInput type="password" autoComplete="off" label="DeepSeek API Key（可留空读取 settings.local.json）"
                value={aiKey} onChange={e=>setAiKey(e.currentTarget.value)}
                data-testid="candidate-ai-key"/>
              <Checkbox checked={aiConsent} onChange={e=>setAiConsent(e.currentTarget.checked)}
                label="我明确同意将相关经历、目标岗位和诊断证据发送给 DeepSeek 进行辅助解读"
                data-testid="candidate-ai-consent"/>
              <Text size="xs" c="dimmed">默认只运行本地规则。外部解读即使失败，也不影响五维确定性评分；定性内容仍需本人核实。</Text>
            </Stack>}
          </Panel>
          <Group justify="space-between" mt="xl">
            <Button variant="subtle" leftSection={<IconArrowLeft size={16}/>} onClick={()=>setStep(1)}>返回修改简历</Button>
            <Button onClick={generate} disabled={!readyTarget||!!busy||(aiEnabled&&!aiConsent)}
              rightSection={<IconSparkles size={17}/>} data-testid="candidate-generate">
              生成五维诊断报告
            </Button>
          </Group>
        </>}

        {step===3&&report&&<>
          <StepTitle code="04" title="HR 视角诊断报告">依据校对后的文本分析。每个结论都保留依据位置；不掌握的资料会明确标为“未体现”，不会被视为事实证明。</StepTitle>
          <div className="diag-report-meta"><div><strong>岗位：{target.role||'未提供'} </strong> / 公司：{target.company||'未提供'}</div>
            <div>生成时间 {report.meta.generated_at} · 规则版本 {report.meta.rules_version}</div></div>
          {report.meta.ai_narrative&&<Alert mb="lg" color={report.meta.ai_narrative==='completed'?'teal':'orange'} variant="light">
            {report.meta.ai_notice}
          </Alert>}
          {SECTIONS.map(([key,label],i)=>{
            const data=report.dimensions?.[key];
            const Component=REPORT_COMPONENTS[key];
            return <Panel key={key} testId={'dimension-'+key}
              title={<Group gap="xs" align="center"><span className="diag-section-index">{String(i+1).padStart(2,'0')}</span>{label}</Group>}
              extra={<Status text={data?.status==='ok'?'已生成':data?.status==='disabled'?'已关闭':'生成失败'}
                color={data?.status==='ok'?'teal':'gray'}/>}>
              {data?.status==='ok'?<><Component data={data}/>{data.ai_commentary&&<Alert mt="lg" color="blue" variant="light" title="DeepSeek 辅助解读（仍需核实）">{data.ai_commentary}</Alert>}</>:<Text size="sm" c="dimmed">{data?.conclusion||'暂无结果'}</Text>}
            </Panel>;
          })}
          <Panel title="面试核查清单预览" extra={<Status text={questionList.length+' 条'} color="gray"/>}>
            {questionList.length ? questionList.slice(0,4).map(q=><div className="diag-question" key={q.id}>
              <strong>{q.check}</strong><Text size="sm">{q.question}</Text><Text size="xs" c="dimmed">{q.purpose}</Text>
            </div>):<Text size="sm" c="dimmed">未识别到需要生成核查问题的高/中风险存疑点。</Text>}
          </Panel>
          <Alert color="orange" variant="light" mt="xl" icon={<IconInfoCircle size={18}/>} title="测量边界">
            {report.meta.disclaimer}
          </Alert>
          <Group justify="space-between" mt="xl">
            <Button variant="subtle" leftSection={<IconArrowLeft size={16}/>} onClick={()=>setStep(2)}>返回修改目标</Button>
            <Button rightSection={<IconArrowRight size={16}/>} onClick={()=>setStep(4)} data-testid="candidate-next-todo">查看优化建议 · 逐项采纳</Button>
          </Group>
        </>}

        {step===4&&report&&<>
          <StepTitle code="05" title="选择你真正认可的优化建议">报告不代写整篇简历。只勾选你认为有用且符合事实的改进项，再生成个人待办清单。</StepTitle>
          <Panel title="优化建议清单" extra={<Status text={selected.length+' / '+suggestions.length+' 已勾选'} color="indigo"/>}>
            {suggestions.map(s=><div className="diag-advice" key={s.id} data-testid={'advice-'+s.id}>
              <Checkbox checked={selected.includes(s.id)} label={<Group gap="sm"><Status text={s.priority+'优先级'} color={s.priority==='高'?'orange':s.priority==='中'?'blue':'gray'}/><Status text={s.assessment||'需要修正'} color={s.assessment==='可选深化'?'gray':'orange'}/><strong>{s.title}</strong></Group>}
                onChange={e=>checkboxSetter(selected,setSelected,s.id,e.currentTarget.checked)}/>
              <div className="diag-advice-body">
                <Text size="xs" c="dimmed">定位：{s.location}</Text>
                <Text size="sm">原文：{s.original}</Text>
                {s.related_location&&<Text size="sm" data-testid="advice-opposing-claim">
                  对照：{s.related_location} · {s.related_original}
                </Text>}
                <Text size="sm"><strong>{s.assessment==='可选深化'?'优化机会：':'问题：'}</strong>{s.problem}</Text>
                <Text size="sm"><strong>建议：</strong>{s.action}</Text>
                <div className="diag-example"><strong>局部示例（不是事实陈述）</strong><div>{s.example}</div></div>
              </div>
            </div>)}
            <Group mt="lg" gap="sm" wrap="wrap">
              <Button disabled={!selected.length||!!busy} onClick={()=>exportSelected('todo','txt')}
                leftSection={<IconDownload size={16}/>} data-testid="candidate-download-txt">导出勾选项 TXT</Button>
              <Button variant="light" disabled={!selected.length||!!busy} onClick={()=>exportSelected('todo','pdf')}
                leftSection={<IconDownload size={16}/>} data-testid="candidate-download-pdf">导出勾选项 PDF</Button>
            </Group>
            <Alert color="blue" variant="light" mt="lg" title="继续完成岗位简历">
              把当前已核对的履历、目标岗位与已选建议交给经典编辑器。
              建议不会自动改写简历；进入后需要再次核对内容，才能导出 Word/PDF。
              数据仅在当前浏览器标签页中一次性交接，不发送给外部 AI。
            </Alert>
            <Button mt="md" variant="light" leftSection={<IconFileText size={17}/>}
              onClick={openClassicWithReviewedDraft} disabled={!!busy}
              data-testid="candidate-open-classic">继续编辑并导出岗位简历</Button>
          </Panel>
          <Panel title="面试核查清单" extra={<Status text={selectedQuestions.length+' / '+questionList.length+' 已勾选'} color="gray"/>}>
            {(questionList.length===0)&&<Text size="sm" c="dimmed">当前没有规则触发的高/中风险核查问题。</Text>}
            {questionList.map(q=><div className="diag-question" key={q.id}>
              <Checkbox checked={selectedQuestions.includes(q.id)}
                label={<strong>{q.check}</strong>}
                onChange={e=>checkboxSetter(selectedQuestions,setSelectedQuestions,q.id,e.currentTarget.checked)}/>
              <Text size="sm" mt={6}>建议提问：{q.question}</Text>
              <Text size="xs" c="dimmed">想确认什么：{q.purpose}</Text>
            </div>)}
            <Group mt="lg"><Button size="sm" variant="light"
              disabled={!selectedQuestions.length||!!busy} onClick={()=>exportSelected('questions','txt')}>导出核查问题 TXT</Button>
              <Button size="sm" variant="light"
              disabled={!selectedQuestions.length||!!busy} onClick={()=>exportSelected('questions','pdf')}>导出核查问题 PDF</Button></Group>
          </Panel>
          <Group justify="space-between" mt="xl"><Button variant="subtle" leftSection={<IconArrowLeft size={16}/>} onClick={()=>setStep(3)}>返回诊断报告</Button>
            <Button variant="light" leftSection={<IconRefresh size={15}/>} onClick={()=>setStep(1)}>重新校对简历</Button></Group>
        </>}

        <div className="diag-footer"><span>PaperPro · Candidate Intelligence</span><span>规则透明 · 逐条证据 · 人工确认 · 不自动修改原简历</span></div>
      </main>
    </div>
  </div>;
}
