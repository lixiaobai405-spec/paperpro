import { test, expect } from '@playwright/test';
import fs from 'node:fs/promises';

async function startReport(page, { disableExperience = false } = {}) {
  await page.goto('/');
  await page.getByRole('button', { name: '填入虚构演示资料' }).click();
  await page.getByTestId('candidate-parse-text').click();
  await page.getByTestId('candidate-next-target').click();
  await page.getByTestId('candidate-target-role').fill('后端开发工程师');
  if (disableExperience) {
    await page.getByRole('checkbox', { name: '工作经验研判' }).uncheck();
  }
  const pending = page.waitForResponse(response =>
    response.url().endsWith('/api/diagnosis/report')
    && response.request().method() === 'POST'
  );
  await page.getByTestId('candidate-generate').click();
  const response = await pending;
  expect(response.ok()).toBe(true);
  await expect(page.getByTestId('candidate-full-report-export')).toBeVisible();
  return response.json();
}

test('the complete diagnosis report is downloadable as TXT with its frozen version', async ({ page }) => {
  const report = await startReport(page);
  const sent = page.waitForRequest(request =>
    request.url().endsWith('/api/diagnosis/report/export')
    && request.postDataJSON()?.format === 'txt'
  );
  const download = page.waitForEvent('download');
  await page.getByTestId('candidate-export-report-txt').click();
  const request = await sent;
  expect(request.postDataJSON().report.meta).toEqual(report.meta);
  const file = await download;
  const content = (await fs.readFile(await file.path())).toString('utf8');
  expect(content).toContain('PaperPro 五维诊断报告');
  expect(content).toContain(report.meta.generated_at);
  expect(content).toContain(report.meta.reviewed_draft_sha256);
  expect(content).toContain('岗位匹配度量化：已完成');
  expect(content).toContain('原文证据');
  expect(content).toContain('不代表企业录取概率');
});

test('a disabled dimension is named as disabled in the exported partial report', async ({ page }) => {
  const report = await startReport(page, { disableExperience: true });
  expect(report.dimensions.experience.status).toBe('disabled');
  await expect(page.getByTestId('candidate-partial-report')).toContainText('4/5');
  const pending = page.waitForEvent('download');
  await page.getByTestId('candidate-export-report-txt').click();
  const downloaded = await pending;
  const text = (await fs.readFile(await downloaded.path())).toString('utf8');
  expect(text).toContain('部分报告（4/5 项已完成）');
  expect(text).toContain('工作经验研判：已关闭');
  expect(text).not.toContain('全部已完成');
  await expect(page.getByTestId('dimension-match')).toBeVisible();
});

test('the report PDF is a real PDF and export does not change report state', async ({ page }) => {
  await startReport(page);
  const pending = page.waitForEvent('download');
  await page.getByTestId('candidate-export-report-pdf').click();
  const download = await pending;
  const content = await fs.readFile(await download.path());
  expect(content.subarray(0,4).toString()).toBe('%PDF');
  await expect(page.getByTestId('dimension-match')).toBeVisible();
  await expect(page.getByTestId('candidate-recommend-primary-cta')).toBeEnabled();
});

test('all diagnostic dimensions disabled means no empty report may be started', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: '填入虚构演示资料' }).click();
  await page.getByTestId('candidate-parse-text').click();
  await page.getByTestId('candidate-next-target').click();
  await page.getByTestId('candidate-target-role').fill('后端开发工程师');
  for (const label of [
    '岗位匹配度量化', '工作经验研判', '学习能力与发展潜力',
    '岗位重视度', '简历智能验真',
  ]) {
    await page.getByRole('checkbox', { name: label }).uncheck();
  }
  await expect(page.getByTestId('candidate-no-dimensions')).toBeVisible();
  await expect(page.getByTestId('candidate-generate')).toBeDisabled();
});

test('report export failure is visible without discarding current diagnosis', async ({ page }) => {
  await startReport(page);
  await page.route('**/api/diagnosis/report/export', route =>
    route.fulfill({
      status: 500, contentType: 'application/json',
      body: JSON.stringify({detail: 'PDF 生成失败，请先尝试文本导出'})
    })
  );
  await page.getByTestId('candidate-export-report-pdf').click();
  await expect(page.getByText('PDF 生成失败，请先尝试文本导出')).toBeVisible();
  await expect(page.getByTestId('candidate-export-report-txt')).toBeEnabled();
  await expect(page.getByTestId('dimension-match')).toBeVisible();
});
