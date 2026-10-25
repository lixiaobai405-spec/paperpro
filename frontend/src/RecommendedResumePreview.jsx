import { Badge, Group, Text, Title } from '@mantine/core';

const text = (value) => typeof value === 'string' ? value.trim() : '';
const lines = (value) => Array.isArray(value) ? value.filter((item) => text(item)) : [];

function Section({ title, children }) {
  return <section className="recommended-section">
    <h3>{title}</h3>
    {children}
  </section>;
}

function Entries({ entries, kind }) {
  return lines(entries?.map?.((entry) => entry?.heading) || []).length || entries?.some?.(entry => lines(entry?.bullets || entry?.details).length)
    ? <Section title={kind === 'experience' ? '工作与实习经历' : kind === 'projects' ? '项目经历' : '教育背景'}>
      {(entries || []).map((entry, i) => {
        const heading = kind === 'experience'
          ? [text(entry.company), text(entry.role)].filter(Boolean).join(' ｜ ') || text(entry.heading)
          : text(entry.heading);
        const dates = kind === 'experience'
          ? [text(entry.start_date), text(entry.end_date)].filter(Boolean).join(' — ')
          : '';
        const bullets = lines(kind === 'education' ? entry.details : entry.bullets);
        if (!heading && !bullets.length && !dates) return null;
        return <div className="recommended-entry" key={i}>
          {(heading||dates)&&<div className="recommended-entry-head">
            {heading&&<strong>{heading}</strong>}
            {dates&&<span>{dates}</span>}
          </div>}
          {bullets.length>0&&<ul>{bullets.map((bullet,j)=><li key={j}>{bullet}</li>)}</ul>}
        </div>;
      })}
    </Section> : null;
}

export default function RecommendedResumePreview({ draft }) {
  if (!draft) return null;
  const contact = [text(draft.email), text(draft.phone), text(draft.location), ...lines(draft.links)];
  const skills = lines(draft.skills);
  const additional = lines(draft.additional);
  const certificates = lines(draft.certificates);
  const selfEvaluation = text(draft.self_evaluation);
  const hasIntro = text(draft.summary);
  return <article className="recommended-paper" data-testid="recommended-resume-preview">
    <header className="recommended-head">
      <Title order={2}>{text(draft.name) || '简历草稿'}</Title>
      {text(draft.title)&&<Text fw={650} size="sm">{draft.title}</Text>}
      {contact.some(Boolean)&&<div className="recommended-contacts">
        {contact.filter(Boolean).map((line,i)=><span key={i}>{line}</span>)}
      </div>}
    </header>
    {hasIntro&&<Section title="个人简介"><p>{draft.summary}</p></Section>}
    {skills.length>0&&<Section title="专业技能">
      <div className="recommended-skills">{skills.map((skill,i)=><span key={i}>{skill}</span>)}</div>
    </Section>}
    <Entries entries={draft.experience} kind="experience"/>
    <Entries entries={draft.projects} kind="projects"/>
    <Entries entries={draft.education} kind="education"/>
    {certificates.length>0&&<Section title="证书与资质"><ul>{certificates.map((item,i)=><li key={i}>{item}</li>)}</ul></Section>}
    {selfEvaluation&&selfEvaluation!==hasIntro&&<Section title="自我评价"><p>{selfEvaluation}</p></Section>}
    {additional.length>0&&<Section title="其他内容（请核对）">
      <ul>{additional.map((item,i)=><li key={i}>{item}</li>)}</ul>
    </Section>}
    <Group justify="flex-end" mt="md"><Badge size="sm" variant="light" color="gray">可编辑推荐稿 · 未自动采用</Badge></Group>
  </article>;
}
