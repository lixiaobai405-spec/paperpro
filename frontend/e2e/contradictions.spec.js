import { test, expect } from '@playwright/test';
import fs from 'node:fs/promises';

test('two opposing current resume statements are visible, reviewable and exported together', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: '填入虚构演示资料' }).click();
  await page.getByTestId('candidate-parse-text').click();
  await page.getByLabel('个人简介').fill('我熟悉 Python，可进行 API 开发。');
  await page.getByLabel('技能（每行一项）').fill('Python：不会\nSQL');
  await page.getByTestId('candidate-next-target').click();
  await page.getByTestId('candidate-target-role').fill('后端开发工程师');
  await page.getByTestId('candidate-generate').click();

  const conflicting = page.getByTestId('dimension-verification')
    .locator('.diag-issue')
    .filter({ hasText: '描述可能不一致' });
  await expect(conflicting).toHaveCount(1);
  await expect(conflicting).toContainText('我熟悉 Python');
  await expect(conflicting.getByTestId('verification-opposing-claim')).toContainText('skills.0');
  await expect(conflicting.getByTestId('verification-opposing-claim')).toContainText('Python：不会');

  await page.getByTestId('candidate-next-todo').click();
  const advice = page.locator('[data-testid^="advice-advice-claim-conflict-"]');
  await expect(advice).toHaveCount(1);
  await expect(advice).toContainText('可能不一致');
  await expect(advice).toContainText('可选深化');
  await expect(advice.getByTestId('advice-opposing-claim')).toContainText('Python：不会');
  await advice.locator('input[type="checkbox"]').check();

  const downloaded = page.waitForEvent('download');
  await page.getByTestId('candidate-download-txt').click();
  const item = await downloaded;
  const output = (await fs.readFile(await item.path())).toString('utf8');
  expect(output).toContain('原文：我熟悉 Python');
  expect(output).toContain('对照位置：skills.0');
  expect(output).toContain('对照原文：Python：不会');

  await page.getByRole('button', { name: '返回诊断报告' }).click();
  await page.getByRole('button', { name: '返回修改目标' }).click();
  await page.getByRole('button', { name: '返回修改简历' }).click();
  await page.getByLabel('技能（每行一项）').fill('Python\nSQL');
  await page.getByTestId('candidate-next-target').click();
  await page.getByTestId('candidate-generate').click();
  await expect(page.getByTestId('dimension-verification')
    .locator('.diag-issue')
    .filter({ hasText: '描述可能不一致' })).toHaveCount(0);
});
