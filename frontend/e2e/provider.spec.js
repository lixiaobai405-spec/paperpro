import { test, expect } from '@playwright/test';

test('switching providers clears the previous provider key and consent', async ({ page }) => {
  await page.goto('/');
  await page.getByTestId('demo-button').click();
  await page.getByText('AI 智能润色', { exact: true }).click();
  await page.getByRole('button', { name: 'AI 设置' }).click();
  const keyField = page.getByRole('textbox', { name: /API Key/ });
  const consent = page.getByRole('checkbox', { name: /我同意仅在主动点击 AI 优化/ });
  await keyField.fill('DEEPSEEK_ONLY_PLACEHOLDER');
  await consent.check();
  await page.getByRole('button', { name: '保存本次会话设置' }).click();

  await page.getByTestId('ai-provider').getByText('自定义 API').click();
  await page.getByRole('button', { name: 'AI 设置' }).click();
  await expect(page.getByRole('textbox', { name: /API Key/ })).toHaveValue('');
  await expect(page.getByRole('checkbox', { name: /我同意仅在主动点击 AI 优化/ })).not.toBeChecked();
});

test('DeepSeek selected in UI sends only allowlisted provider name', async ({ page }) => {
  await page.goto('/');
  await page.getByTestId('demo-button').click();
  await page.getByText('AI 智能润色', { exact: true }).click();
  await expect(page.getByTestId('ai-provider')).toBeVisible();
  let body;
  await page.getByRole('button', { name: 'AI 设置' }).click();
  await page.getByRole('textbox', { name: /API Key/ }).fill('PLACEHOLDER_TOKEN');
  await page.getByRole('checkbox', { name: /我同意仅在主动点击 AI 优化/ }).check();
  await page.getByRole('button', { name: '保存本次会话设置' }).click();
  await page.route('**/api/enhance', async (route) => {
    body = route.request().postDataJSON();
    await route.fulfill({
      status: 200, contentType: 'application/json',
      body: JSON.stringify({ resume: body.resume, changes: [], mode: 'ai', warnings: [] }),
    });
  });
  await page.getByTestId('enhance-button').click();
  await expect.poll(() => body?.provider).toBe('deepseek');
  expect(body.use_ai).toBe(true);
  // Testing never sends this placeholder to an external provider.
  expect(body.api_key).toBe('PLACEHOLDER_TOKEN');
});
