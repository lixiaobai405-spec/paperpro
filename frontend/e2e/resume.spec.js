import { test, expect } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import path from 'node:path';

test('home, demo, editor, fact confirmation and two real downloads', async ({ page }) => {
  const pageErrors = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));
  await page.goto('/');
  await expect(page.getByText('让经历清晰，让机会')).toBeVisible();
  await expect(page.getByTestId('file-dropzone')).toBeVisible();
  await page.getByTestId('demo-button').click();
  await expect(page.getByTestId('editor-panel')).toBeVisible();
  await expect(page.getByTestId('resume-preview')).toContainText('陈晓明');
  await expect(page.getByTestId('download-pdf')).toBeDisabled();

  await page.getByTestId('field-name').fill('王小明');
  await expect(page.getByTestId('resume-preview')).toContainText('王小明');
  await page.getByTestId('source-details').locator('summary').click();
  await expect(page.getByTestId('source-details')).toContainText('星辰科技');
  await page.getByTestId('review-checkbox').check();
  await expect(page.getByTestId('download-pdf')).toBeEnabled();

  const [word] = await Promise.all([
    page.waitForEvent('download', { timeout: 40_000 }),
    page.getByTestId('download-docx').click(),
  ]);
  expect(word.suggestedFilename()).toBe('paperpro_resume.docx');
  expect(await word.failure()).toBeNull();

  const [pdf] = await Promise.all([
    page.waitForEvent('download', { timeout: 60_000 }),
    page.getByTestId('download-pdf').click(),
  ]);
  expect(pdf.suggestedFilename()).toBe('paperpro_resume.pdf');
  expect(await pdf.failure()).toBeNull();
  // Verify that downloaded files contain the *user-edited* name, not
  // merely that the browser received a successful download response.
  const check = [
    'import sys, pymupdf',
    'from docx import Document',
    'data = "\\n".join(p.text for p in Document(sys.argv[1]).paragraphs) if sys.argv[2] == "docx" else "\\n".join(p.get_text() for p in pymupdf.open(sys.argv[1]))',
    'print("MATCH" if "王小明" in data else "MISSING")',
  ].join('\n');
  for (const [download, format] of [[word, 'docx'], [pdf, 'pdf']]) {
    const status = execFileSync('uv', [
      'run', '--python', '3.12', 'python', '-c', check,
      await download.path(), format,
    ], { cwd: path.resolve('..'), encoding: 'utf8', timeout: 50_000 });
    expect(status.trim()).toBe('MATCH');
  }
  expect(pageErrors).toEqual([]);
});

test('real scanned PNG browser upload follows extraction + edit workflow', async ({ page }) => {
  await page.goto('/');
  const png = await page.evaluate(() => {
    const canvas = document.createElement('canvas');
    canvas.width = 1500; canvas.height = 360;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#000000'; ctx.font = 'bold 78px Arial';
    ctx.fillText('ALEX CHEN RESUME', 45, 140);
    return canvas.toDataURL('image/png').split(',')[1];
  });
  await page.locator('input[type="file"]').first().setInputFiles({
    name: 'candidate_scan.png', mimeType: 'image/png', buffer: Buffer.from(png, 'base64'),
  });
  await expect(page.getByTestId('editor-panel')).toBeVisible({ timeout: 90_000 });
  await expect(page.getByTestId('resume-preview')).toContainText('ALEX');
  await expect(page.getByText('candidate_scan.png')).toBeVisible();
  await expect(page.getByText(/扫描图片经过 OCR/)).toBeVisible();
});

test('invalid upload exposes error instead of fake success', async ({ page }) => {
  await page.goto('/');
  await page.locator('input[type="file"]').first().setInputFiles({
    name: 'broken.pdf', mimeType: 'application/pdf', buffer: Buffer.from('this is not a PDF'),
  });
  await expect(page.getByText('操作未完成')).toBeVisible();
  await expect(page.getByTestId('editor-panel')).toHaveCount(0);
});

test('local enhancement does not require API and cannot bypass review gate', async ({ page }) => {
  await page.goto('/');
  await page.getByTestId('demo-button').click();
  await page.getByTestId('review-checkbox').check();
  await page.getByTestId('enhance-button').click();
  await expect(page.getByTestId('download-pdf')).toBeDisabled();
  await page.getByTestId('review-checkbox').check();
  await page.getByTestId('field-name').fill('重新编辑姓名');
  await expect(page.getByTestId('download-pdf')).toBeDisabled();
});

test('external AI is gated on explicit consent', async ({ page }) => {
  await page.goto('/');
  await page.getByTestId('demo-button').click();
  await page.getByText('AI 智能润色', { exact: true }).click();
  await page.getByTestId('enhance-button').click();
  await expect(page.getByText('AI 服务与隐私设置')).toBeVisible();
  await expect(page.getByText('我同意仅在主动点击 AI 优化时将本次简历内容发送给所配置的服务。')).toBeVisible();
});

test('mobile viewport has no horizontal overflow and controls are reachable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await page.getByTestId('demo-button').click();
  await expect(page.getByTestId('resume-preview')).toBeVisible();
  const positions = await page.evaluate(() => ({
    input: document.querySelector('.studio-left').getBoundingClientRect().top + window.scrollY,
    preview: document.querySelector('.studio-right').getBoundingClientRect().top + window.scrollY,
  }));
  expect(positions.input).toBeLessThan(positions.preview);
  const sizes = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  expect(sizes.scroll).toBeLessThanOrEqual(sizes.width + 2);
  await page.getByTestId('field-name').fill('Mobile');
  await expect(page.getByTestId('resume-preview')).toContainText('Mobile');
});
