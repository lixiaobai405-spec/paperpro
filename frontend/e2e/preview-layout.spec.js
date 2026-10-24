import { test, expect } from '@playwright/test';

async function previewBounds(page) {
  return page.evaluate(() => {
    const box = (selector) => {
      const bounds = document.querySelector(selector).getBoundingClientRect();
      return { top: bounds.top, bottom: bounds.bottom, width: bounds.width, height: bounds.height };
    };
    const sheet = document.querySelector('[data-testid="resume-preview"]');
    return {
      sheet: box('[data-testid="resume-preview"]'),
      lastLine: box('.paper-section:last-child li:last-child'),
      canvas: box('.preview-canvas'),
      hint: box('.preview-hint'),
      source: box('.source-details'),
      footer: box('.footer'),
      bottomPadding: parseFloat(getComputedStyle(sheet).paddingBottom),
      scrollHeight: sheet.scrollHeight,
      clientHeight: sheet.clientHeight,
      viewportWidth: document.documentElement.clientWidth,
      documentWidth: document.documentElement.scrollWidth,
    };
  });
}

for (const width of [1920, 1366, 1024, 390]) {
  test(`long classic preview stays on the paper without overlapping controls at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    page.on('console', (message) => {
      if (message.type() === 'error') errors.push(message.text());
    });
    // This layout regression is entirely local; it needs no server key or AI request.
    await page.route('**/api/config', (route) => route.fulfill({ json: {} }));
    await page.goto('/classic');
    await expect(page).toHaveTitle('PaperPro · 智能简历工作台');
    const empty = await page.getByTestId('resume-preview-empty').boundingBox();
    expect(empty.height / empty.width).toBeCloseTo(297 / 210, 2);

    await page.getByTestId('demo-button').click();
    await page.getByText('其他信息 / 未分类内容', { exact: true }).click();
    const additional = page.locator('.mantine-Accordion-item')
      .filter({ hasText: '其他信息 / 未分类内容' }).locator('textarea');
    const lines = Array.from({ length: 24 }, (_, index) =>
      `补充说明 ${index + 1}：参与需求分析、前后端接口联调、异常排查及回归验证，保留完整测试内容。`);
    lines.push(`项目链接：https://example.com/${'long-path-'.repeat(18)}`);
    lines.push('末尾核对标记：所有补充内容都应完整显示在白色纸张内部。');
    await additional.fill(lines.join('\n'));
    await expect(page.getByTestId('resume-preview')).toContainText(lines.at(-1));
    await page.evaluate(() => document.fonts.ready);

    const long = await previewBounds(page);
    expect(long.lastLine.bottom + long.bottomPadding).toBeLessThanOrEqual(long.sheet.bottom + 2);
    expect(long.scrollHeight).toBeLessThanOrEqual(long.clientHeight + 1);
    expect(long.sheet.bottom).toBeLessThanOrEqual(long.canvas.bottom);
    expect(long.canvas.bottom).toBeLessThan(long.hint.top);
    expect(long.hint.bottom).toBeLessThan(long.source.top);
    expect(long.source.bottom).toBeLessThan(long.footer.top);
    expect(long.documentWidth).toBeLessThanOrEqual(long.viewportWidth + 1);

    // Growing and shrinking the draft must keep controls in normal document flow.
    await page.getByTestId('source-details').locator('summary').click();
    await expect(page.locator('.source-text')).toBeVisible();
    await additional.fill('简短的补充信息');
    await expect(page.getByTestId('resume-preview')).not.toContainText(lines.at(-1));
    const short = await previewBounds(page);
    expect(short.sheet.height).toBeLessThan(long.sheet.height);
    expect(short.sheet.height).toBeGreaterThanOrEqual(short.sheet.width * 297 / 210 - 1);
    expect(short.lastLine.bottom + short.bottomPadding).toBeLessThanOrEqual(short.sheet.bottom + 2);
    expect(short.source.bottom).toBeLessThan(short.footer.top);
    expect(errors).toEqual([]);
  });
}
