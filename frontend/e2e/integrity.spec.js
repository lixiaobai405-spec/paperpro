import { test, expect } from '@playwright/test';

test('editing comma-separated skills keeps the character being typed', async ({ page }) => {
  await page.goto('/');
  await page.getByTestId('demo-button').click();
  const skills = page.getByRole('textbox', { name: '专业技能' });
  await skills.focus();
  await skills.press('End');
  await skills.type('，GraphQL', { delay: 15 });
  await expect(skills).toHaveValue(/Git，GraphQL$/);
  await expect(page.getByTestId('resume-preview')).toContainText('GraphQL');
});

test('editing multi-line work details preserves newlines while typing', async ({ page }) => {
  await page.goto('/');
  await page.getByTestId('demo-button').click();
  const bullets = page.getByTestId('工作经历').locator('textarea').first();
  await bullets.focus();
  await bullets.press('ControlOrMeta+End');
  await bullets.press('Enter');
  await expect(bullets).toHaveValue(/\n$/);
  await bullets.type('新增工作描述');
  await expect(bullets).toHaveValue(/\n新增工作描述$/);
  await expect(page.getByTestId('resume-preview')).toContainText('新增工作描述');
});

test('outdated enhancement response does not erase edits made after submission', async ({ page }) => {
  await page.goto('/');
  await page.getByTestId('demo-button').click();
  let finishResponse;
  let received;
  const intercepted = new Promise((resolve) => { received = resolve; });
  await page.route('**/api/enhance', async (route) => {
    const input = route.request().postDataJSON();
    finishResponse = () => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        resume: { ...input.resume, name: 'OLD RESPONSE NAME' },
        changes: [],
        mode: 'local',
        warnings: [],
      }),
    });
    received();
  });
  await page.getByTestId('enhance-button').click();
  await intercepted;
  await page.getByTestId('field-name').fill('LAST EDIT WINS');
  finishResponse();
  await expect(page.getByTestId('resume-preview')).toContainText('LAST EDIT WINS');
  await expect(page.getByTestId('resume-preview')).not.toContainText('OLD RESPONSE NAME');
});

for (const contextField of ['目标岗位（可选）', '岗位描述（可选）']) {
  test('editing ' + contextField + ' while AI runs must reject stale suggestions', async ({ page }) => {
    await page.goto('/');
    await page.getByTestId('demo-button').click();
    await page.getByText('AI 智能润色', { exact: true }).click();
    await page.getByRole('button', { name: 'AI 设置' }).click();
    await page.getByRole('textbox', { name: /API Key/ }).fill('MOCK_TOKEN');
    await page.getByRole('checkbox', { name: /我同意仅在主动点击 AI 优化/ }).check();
    await page.getByRole('button', { name: '保存本次会话设置' }).click();
    let fulfill;
    let signal;
    const intercepted = new Promise((resolve) => { signal = resolve; });
    await page.route('**/api/enhance', async (route) => {
      const prior = route.request().postDataJSON().resume;
      fulfill = () => route.fulfill({
        status: 200, contentType: 'application/json',
        body: JSON.stringify({
          resume: { ...prior, summary: 'STALE AI OUTPUT' },
          changes: [{ field: 'summary', before: prior.summary, after: 'STALE AI OUTPUT' }],
          mode: 'ai', warnings: [],
        }),
      });
      signal();
    });
    await page.getByTestId('enhance-button').click();
    await intercepted;
    await page.getByRole('textbox', { name: contextField }).fill('新岗位要求');
    fulfill();
    await expect(page.getByText(/旧版本的润色结果/)).toBeVisible();
    await expect(page.getByTestId('changes-list')).toHaveCount(0);
    await expect(page.getByTestId('resume-preview')).not.toContainText('STALE AI OUTPUT');
  });
}

test('AI does not apply qualitative edits until explicit human approval', async ({ page }) => {
  await page.goto('/');
  await page.getByTestId('demo-button').click();
  await page.getByText('AI 智能润色', { exact: true }).click();
  await page.getByRole('button', { name: 'AI 设置' }).click();
  await page.getByRole('textbox', { name: /API Key/ }).fill('TEST-ONLY');
  await page.getByRole('checkbox', { name: /我同意仅在主动点击 AI 优化/ }).check();
  await page.getByRole('button', { name: '保存本次会话设置' }).click();
  await page.route('**/api/enhance', async (route) => {
    const previous = route.request().postDataJSON().resume;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        resume: { ...previous, summary: '在微软担任过首席技术官' },
        changes: [{ field: 'summary', before: previous.summary, after: '在微软担任过首席技术官' }],
        mode: 'ai',
        warnings: ['逐项核实事实。'],
      }),
    });
  });
  await page.getByTestId('enhance-button').click();
  await expect(page.getByTestId('changes-list')).toBeVisible();
  await expect(page.getByTestId('resume-preview')).not.toContainText('在微软担任过首席技术官');
  const apply = page.getByRole('button', { name: '应用已批准的修改' });
  const proposal = page.getByRole('checkbox', { name: /在微软担任过首席技术官/ });
  await expect(apply).toBeDisabled();
  await expect(proposal).toBeVisible();
  await expect(page.getByTestId('review-checkbox')).toBeDisabled();
  await proposal.check();
  await apply.click();
  await expect(page.getByTestId('resume-preview')).toContainText('在微软担任过首席技术官');
  await expect(page.getByTestId('download-docx')).toBeDisabled();
});
