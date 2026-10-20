// One-shot, user-initiated transfer between the existing diagnosis and classic UIs.
// Only this browser tab stores the draft, until it is consumed on /classic.
// No server persistence, AI request, auto-rewrite, or export approval is involved.
export const HANDOFF_KEY = 'paperpro-candidate-to-classic-v1';
const HANDOFF_AGE_MS = 30 * 60 * 1000;

const nonblank = (value) => typeof value === 'string' ? value.trim() : '';
const strings = (values) => Array.isArray(values)
  ? values.filter((value) => typeof value === 'string') : [];

function reviewedAdditional(candidate) {
  const additional = strings(candidate.additional).slice();
  // Classic has no dedicated certificate/self-evaluation fields.
  // Preserve them without repeating content already present in raw other
  // details or the candidate's summary. Never invent missing credentials.
  const key = (text) => nonblank(text).replace(/\s+/g, '').toLowerCase();
  // A keyword appearing in a summary is not proof that the certificate or
  // self-evaluation was already exported. Deduplicate only complete entries.
  const existingCertificates = new Set(additional.map((text) =>
    key(text.replace(/^\s*证书\s*[:：]\s*/, ''))
  ));
  for (const certificate of strings(candidate.certificates)) {
    if (!key(certificate) || existingCertificates.has(key(certificate))) continue;
    additional.push('证书：' + certificate);
    existingCertificates.add(key(certificate));
  }
  const evaluation = nonblank(candidate.self_evaluation);
  const exactEvaluationTexts = [candidate.summary || '', ...strings(candidate.additional)]
    .map((text) => key(text.replace(/^\s*自我评价\s*[:：]\s*/, '')));
  if (evaluation && !exactEvaluationTexts.includes(key(evaluation))) {
    additional.push('自我评价：' + evaluation);
  }
  return additional;
}

function reviewedHeading(entry) {
  const dates = [nonblank(entry.start_date), nonblank(entry.end_date)]
    .filter(Boolean).join(' — ');
  const role = [nonblank(entry.company), nonblank(entry.role)]
    .filter(Boolean).join(' ｜ ');
  // The reviewed structured values outrank the original raw heading.
  // Keep the unmodified source text for comparison in the classic editor.
  return [dates, role].filter(Boolean).join('  ') || nonblank(entry.heading);
}

export function createClassicHandoff(candidate, target, report, selected, fileMeta) {
  if (!candidate || !report?.meta?.reviewed_draft_sha256) {
    throw new Error('请先核对简历并生成当前诊断报告。');
  }
  const selection = new Set(selected);
  const advice = (report.suggestions || [])
    .filter((s) => selection.has(s.id))
    .map((s) => ({
      id: s.id, title: s.title, location: s.location, action: s.action,
    }));
  const classicResume = {
    name: nonblank(candidate.name),
    title: nonblank(candidate.title),
    email: nonblank(candidate.email),
    phone: nonblank(candidate.phone),
    location: nonblank(candidate.location),
    links: strings(candidate.links),
    summary: nonblank(candidate.summary),
    skills: strings(candidate.skills),
    experience: (candidate.experience || []).map((e) => ({
      heading: reviewedHeading(e),
      bullets: strings(e.bullets),
    })),
    projects: (candidate.projects || []).map((e) => ({
      heading: nonblank(e.heading), bullets: strings(e.bullets),
    })),
    education: (candidate.education || []).map((e) => ({
      heading: nonblank(e.heading), details: strings(e.details),
    })),
    additional: reviewedAdditional(candidate),
  };
  const headingComparisons = (candidate.experience || [])
    .map((entry, index) => ({
      index,
      original: nonblank(entry.heading),
      projected: reviewedHeading(entry),
    }))
    .filter((item) => item.original && item.original !== item.projected);
  return {
    version: 1,
    createdAt: Date.now(),
    resume: classicResume,
    targetRole: nonblank(target?.role),
    jobDescription: nonblank(target?.job_description),
    targetCompany: nonblank(target?.company),
    sourceText: nonblank(candidate.source_text),
    sourceHash: nonblank(candidate.source_sha256),
    filename: nonblank(fileMeta?.name),
    headingComparisons,
    advice,
  };
}

export function saveClassicHandoff(storage, payload) {
  storage.setItem(HANDOFF_KEY, JSON.stringify(payload));
}

export function consumeClassicHandoff(storage) {
  const saved = storage.getItem(HANDOFF_KEY);
  if (!saved) return null;
  storage.removeItem(HANDOFF_KEY); // One-shot, even when malformed/expired.
  try {
    const item = JSON.parse(saved);
    if (item?.version !== 1 || !Number.isFinite(item.createdAt)
        || item.createdAt > Date.now() || Date.now() - item.createdAt > HANDOFF_AGE_MS
        || !item.resume || typeof item.resume.name !== 'string'
        || !Array.isArray(item.resume.experience)
        || !Array.isArray(item.advice)) return null;
    return item;
  } catch {
    return null;
  }
}
