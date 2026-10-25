import { test, expect } from '@playwright/test';
import fs from 'node:fs/promises';

const SOURCE = [
  '陈楠',
  '工作经历',
  '2024.01 - 2025.06 示例公司 | 后端工程师',
  '- 使用 Python 进行接口开发',
  '项目经历',
  '订单后台',
  '- 开发 Python 查询接口',
].join('\n');

async function prepare(page) {
  await page.goto('/');
  await page.getByTestId('candidate-paste').fill(SOURCE);
  await page.getByTestId('candidate-parse-text').click();
  await page.getByTestId('candidate-next-target').click();
  await page.getByTestId('candidate-target-role').fill('后端工程师');
  await page.getByTestId('candidate-generate').click();
  await expect(page.getByTestId('dimension-match')).toBeVisible();
  await expect(page.getByTestId('candidate-recommend-primary')).toBeVisible();
  await page.getByTestId('candidate-recommend-primary-cta').click();
  await expect(page.getByTestId('candidate-recommendation-panel')).toBeVisible();
}

test('first deliverable is an entire improved resume, not a list of advice', async ({ page }) => {
  await prepare(page);
  const preview = page.getByTestId('recommended-resume-preview');
  await expect(preview).toContainText('陈楠');
  await expect(preview).toContainText('个人简介');
  await expect(preview).toContainText('相关工作与项目实践');
  await expect(preview).toContainText('示例公司');
  await expect(preview).toContainText('订单后台');
  await expect(page.getByTestId('recommendation-notice')).toContainText('未使用外部 AI');
  await expect(page.getByTestId('candidate-recommend-ai')).toBeDisabled();

  await page.getByTestId('candidate-accept-recommend').click();
  await expect(page).toHaveURL(/\/classic$/);
  await expect(page.getByTestId('resume-preview')).toContainText('相关工作与项目实践');
  await expect(page.getByTestId('review-checkbox')).not.toBeChecked();
  await expect(page.getByTestId('download-docx')).toBeDisabled();
  await page.getByTestId('review-checkbox').check();
  const downloadPromise = page.waitForEvent('download');
  const requestPromise = page.waitForRequest(req => req.url().includes('/api/export?format=docx'));
  await page.getByTestId('download-docx').click();
  const req = await requestPromise;
  expect(req.postDataJSON().resume.summary).toContain('相关工作与项目实践');
  const download = await downloadPromise;
  const result = await fs.readFile(await download.path());
  expect(result.subarray(0,2).toString()).toBe('PK');
});

test('editing the proposed full resume does not mutate source until adoption', async ({ page }) => {
  await prepare(page);
  const editor = page.getByTestId('candidate-recommend-edit');
  await editor.locator('summary').click();
  await editor.getByRole('textbox', { name: '个人简介' }).fill('我自行完善的个人简介');
  await expect(page.getByTestId('recommended-resume-preview')).toContainText('我自行完善的个人简介');
  await expect(page.getByTestId('candidate-open-original')).toBeVisible();
  await page.getByTestId('candidate-accept-recommend').click();
  await expect(page.getByTestId('resume-preview')).toContainText('我自行完善的个人简介');
});

test('external AI recommendation is opt-in and remains a preview until user adopts it', async ({ page }) => {
  let externalCalls = 0;
  await page.route('**/api/diagnosis/recommend', async route => {
    const request = route.request().postDataJSON();
    if (!request.use_ai) {
      const real = await route.fetch();
      await route.fulfill({ response: real });
      return;
    }
    externalCalls++;
    expect(request.ai_consent).toBe(true);
    expect(request.api_key).toBe('FAKE_TEST_ONLY');
    await route.fulfill({json:{
      mode:'ai',
      draft:{
        ...request.resume,
        summary:'AI 示例完整个人简介：参与订单接口开发。',
        projects:[{heading:'订单后台',bullets:['参与订单查询接口开发']}],
      },
      improvements:['整理简介与项目职责'],
      questions:[{id:'date',question:'是否填写项目日期？'}],
      notice:'AI 已生成推荐稿，请核对',
    }});
  });
  await prepare(page);
  await expect(page.getByTestId('recommended-resume-preview')).not.toContainText('AI 示例完整个人简介');
  await page.getByTestId('candidate-recommend-key').fill('FAKE_TEST_ONLY');
  await page.getByTestId('candidate-recommend-consent').check();
  await page.getByTestId('candidate-recommend-ai').click();
  await expect(page.getByTestId('recommended-resume-preview')).toContainText('AI 示例完整个人简介');
  expect(externalCalls).toBe(1);
  await page.getByTestId('candidate-recommend-explained').locator('summary').click();
  await expect(page.getByTestId('candidate-recommend-explained')).toContainText('整理简介与项目职责');
  await expect(page.getByTestId('candidate-recommend-explained')).toContainText('是否填写项目日期');
  await page.getByTestId('candidate-open-original').click();
  await expect(page.getByTestId('resume-preview')).not.toContainText('AI 示例完整个人简介');
});

test('recommendation unavailable still delivers original draft without blocking handoff', async ({ page }) => {
  await page.route('**/api/diagnosis/recommend', route => route.fulfill({
    status:502, contentType:'application/json', body:JSON.stringify({detail:'推荐稿服务暂不可用'})
  }));
  await prepare(page);
  await expect(page.getByTestId('recommendation-notice')).toContainText('暂未完成自动加强');
  await expect(page.getByTestId('recommended-resume-preview')).toContainText('陈楠');
  await page.getByTestId('candidate-accept-recommend').click();
  await expect(page).toHaveURL(/\/classic$/);
  await expect(page.getByTestId('resume-preview')).toContainText('示例公司');
});
