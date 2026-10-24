import { test, expect } from '@playwright/test';

const LOOSE = [
  '陈楠',
  '去年在星河公司做后端，负责 Python 接口和订单服务。',
  '做了库存项目，处理订单同步和接口重试。',
  '最近在找后端岗位，擅长 SQL。',
].join('\n');

test('loose resume completes local report without an AI request', async ({ page }) => {
  let calls = 0;
  await page.route('**/api/diagnosis/ai-structure', async route => {
    calls += 1;
    await route.abort();
  });
  await page.goto('/');
  await page.getByTestId('candidate-paste').fill(LOOSE);
  await page.getByTestId('candidate-parse-text').click();
  await expect(page.getByTestId('candidate-ai-structure-panel')).toBeVisible();
  await expect(page.getByTestId('candidate-structure-request')).toBeDisabled();
  await page.getByTestId('candidate-next-target').click();
  await page.getByTestId('candidate-target-role').fill('后端开发工程师');
  await page.getByTestId('candidate-generate').click();
  await expect(page.getByTestId('dimension-match')).toBeVisible();
  expect(calls).toBe(0);
});

test('AI structure is optional, stale responses are not applied and user accepts the draft', async ({ page }) => {
  let requestCount = 0;
  await page.route('**/api/diagnosis/ai-structure', async route => {
    requestCount += 1;
    const request = route.request().postDataJSON();
    expect(request.ai_consent).toBe(true);
    expect(request.resume.source_text).toBe(LOOSE);
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'proposal',
        resume: {
          ...request.resume,
          name: '陈楠',
          experience: [{
            heading: '星河公司',
            company: '星河公司',
            role: '后端工程师',
            start_date: '',
            end_date: '',
            bullets: ['负责 Python 接口和订单服务'],
          }],
          projects: [{
            heading: '库存同步项目',
            bullets: ['处理订单同步和接口重试'],
          }],
          skills: ['SQL', 'Python'],
        },
      }),
    });
  });
  await page.goto('/');
  await page.getByTestId('candidate-paste').fill(LOOSE);
  await page.getByTestId('candidate-parse-text').click();
  await expect(page.getByTestId('experience-company-0')).toHaveCount(0);
  await page.getByTestId('candidate-structure-key').fill('FAKE_TEST_ONLY');
  await page.getByTestId('candidate-structure-consent').check();
  await page.getByTestId('candidate-structure-request').click();
  await expect(page.getByTestId('candidate-structure-preview')).toContainText('星河公司');
  await expect(page.getByTestId('experience-company-0')).toHaveCount(0); // No auto write
  expect(requestCount).toBe(1);
  await page.getByTestId('candidate-structure-accept').click();
  await expect(page.getByTestId('experience-company-0')).toHaveValue('星河公司');
  await expect(page.getByTestId('candidate-structure-preview')).toHaveCount(0);
  await expect(page.getByTestId('candidate-structure-consent')).not.toBeChecked();
  await page.getByTestId('candidate-next-target').click();
  await page.getByTestId('candidate-target-role').fill('后端开发工程师');
  await page.getByTestId('candidate-generate').click();
  await expect(page.getByTestId('dimension-match')).toBeVisible();
});

test('AI structure failure never blocks manual review and report', async ({ page }) => {
  await page.route('**/api/diagnosis/ai-structure', route =>
    route.fulfill({ status: 502, contentType: 'application/json',
      body: JSON.stringify({ detail: 'AI 服务暂时不可用，可直接继续人工校对和诊断' }) }));
  await page.goto('/');
  await page.getByTestId('candidate-paste').fill(LOOSE);
  await page.getByTestId('candidate-parse-text').click();
  await page.getByTestId('candidate-structure-consent').check();
  await page.getByTestId('candidate-structure-request').click();
  await expect(page.getByText('AI 服务暂时不可用，可直接继续人工校对和诊断')).toBeVisible();
  await page.getByTestId('candidate-next-target').click();
  await page.getByTestId('candidate-target-role').fill('后端开发工程师');
  await page.getByTestId('candidate-generate').click();
  await expect(page.getByTestId('dimension-verification')).toBeVisible();
});

test('AI structure from an obsolete draft is discarded after the user edits the form', async ({ page }) => {
  let releaseReply;
  let notifyIntercept;
  const intercepted = new Promise(resolve => { notifyIntercept = resolve; });
  await page.route('**/api/diagnosis/ai-structure', async route => {
    const previous = route.request().postDataJSON().resume;
    releaseReply = () => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'proposal',
        resume: { ...previous, projects: [{ heading: 'STALE_PROJECT', bullets: ['旧版'] }] },
      }),
    });
    notifyIntercept();
  }, { times: 1 });

  await page.goto('/');
  await page.getByTestId('candidate-paste').fill(LOOSE);
  await page.getByTestId('candidate-parse-text').click();
  await page.getByTestId('candidate-structure-consent').check();
  await page.getByTestId('candidate-structure-request').click();
  await intercepted;
  await page.getByRole('textbox', { name: '个人简介' }).fill('我刚更新了我的简历');
  await releaseReply();
  await expect(page.getByTestId('candidate-structure-preview')).toHaveCount(0);
  await expect(page.getByRole('textbox', { name: '个人简介' }))
    .toHaveValue('我刚更新了我的简历');
  await page.getByTestId('candidate-next-target').click();
  await expect(page.getByTestId('candidate-target-role')).toBeVisible();
});

test('an in-flight optional model request cannot block a normal diagnosis', async ({ page }) => {
  let releaseReply;
  let notifyIntercept;
  const intercepted = new Promise(resolve => { notifyIntercept = resolve; });
  await page.route('**/api/diagnosis/ai-structure', async route => {
    const original = route.request().postDataJSON().resume;
    releaseReply = () => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'proposal', resume: {
        ...original, projects: [{ heading: 'OLD_DRAFT', bullets: ['过期'] }]
      } }),
    });
    notifyIntercept();
  }, { times: 1 });
  await page.goto('/');
  await page.getByTestId('candidate-paste').fill(LOOSE);
  await page.getByTestId('candidate-parse-text').click();
  await page.getByTestId('candidate-structure-consent').check();
  await page.getByTestId('candidate-structure-request').click();
  await intercepted;
  await page.getByTestId('candidate-next-target').click();
  await page.getByTestId('candidate-target-role').fill('后端开发工程师');
  await expect(page.getByTestId('candidate-generate')).toBeEnabled();
  await page.getByTestId('candidate-generate').click();
  await expect(page.getByTestId('dimension-match')).toBeVisible();
  await releaseReply();
  await expect(page.getByTestId('dimension-match')).toBeVisible();
  await expect(page.getByText('OLD_DRAFT')).toHaveCount(0);
});
