import assert from 'node:assert/strict';
import test from 'node:test';

import { createClassicHandoff, HANDOFF_KEY, saveClassicHandoff, consumeClassicHandoff } from '../src/resumeHandoff.js';

const report = { meta: { reviewed_draft_sha256: 'synthetic-fingerprint' }, suggestions: [] };
const base = () => ({
  name: '虚构验证者', title: '工程师', email: '', phone: '',
  location: '', links: [], summary: '', skills: [], experience: [],
  projects: [], education: [], certificates: [],
  self_evaluation: '', additional: [], source_text: '', source_sha256: '',
});

const transfer = (candidate) => createClassicHandoff(
  candidate, {role:'软件工程师',job_description:''}, report, [], {name:'fictional.pdf'}
);

test('a verified certificate survives projection even if only its name appears in the summary', () => {
  const candidate = { ...base(), summary: '参与 PMP 方法论落地，整理团队流程。', certificates: ['PMP'] };
  const exported = transfer(candidate).resume;
  assert.deepEqual(exported.additional, ['证书：PMP']);
  assert.equal(exported.summary, candidate.summary);
});

test('a certificate already present as an exact additional detail is not duplicated', () => {
  const candidate = { ...base(), certificates: ['CET-6'], additional: ['CET-6'] };
  const exported = transfer(candidate).resume;
  assert.deepEqual(exported.additional, ['CET-6']);
});

test('self evaluation is not discarded because the same words appear within a longer summary', () => {
  const candidate = { ...base(), summary: '本人参与稳定性测试工作。', self_evaluation: '稳定性' };
  const exported = transfer(candidate).resume;
  assert.deepEqual(exported.additional, ['自我评价：稳定性']);
});

test('handoff remains single-use and cannot transfer stale drafts', () => {
  const saved = new Map();
  const storage = {
    getItem: (key) => saved.get(key) ?? null,
    setItem: (key, value) => saved.set(key, value),
    removeItem: (key) => saved.delete(key),
  };
  const sample = transfer(base());
  saveClassicHandoff(storage, sample);
  assert.equal(storage.getItem(HANDOFF_KEY) !== null, true);
  assert.deepEqual(consumeClassicHandoff(storage), sample);
  assert.equal(consumeClassicHandoff(storage), null);
  saveClassicHandoff(storage, { ...sample, createdAt: Date.now()-31*60*1000 });
  assert.equal(consumeClassicHandoff(storage), null);
});
