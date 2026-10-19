// Opt-in real browser + DeepSeek smoke test.
// Read key from stdin; do not print, persist, screenshot, or trace it.
// Only the invented demo resume is sent to the paid API.
import { chromium } from 'playwright';
import readline from 'node:readline';

const rl = readline.createInterface({ input: process.stdin, terminal: false });
process.stdout.write('READY_FOR_KEY\n');
const provided = await new Promise((resolve) => rl.once('line', resolve));
rl.close();
let key = provided.trim();
if (!key) {
  process.stdout.write('{"status":"NO_KEY"}\n');
  process.exitCode = 2;
} else {
  let browser;
  try {
    browser = await chromium.launch({ channel: 'chrome', headless: true });
    const context = await browser.newContext({
      acceptDownloads: true,
      viewport: { width: 1400, height: 950 },
    });
    const page = await context.newPage();
    await page.goto('http://127.0.0.1:8766/', { waitUntil: 'networkidle' });
    await page.getByTestId('demo-button').click();
    await page.getByText('AI 智能润色', { exact: true }).click();
    if (!(await page.getByTestId('ai-provider').textContent()).includes('DeepSeek')) {
      throw new Error('DeepSeek provider option missing');
    }
    await page.getByRole('button', { name: 'AI 设置' }).click();
    await page.getByRole('textbox', { name: /API Key/ }).fill(key);
    key = '';
    await page.getByRole('checkbox', { name: /我同意仅在主动点击 AI 优化/ }).check();
    await page.getByRole('button', { name: '保存本次会话设置' }).click();

    const started = Date.now();
    const responseWait = page.waitForResponse(
      (r) => r.url().endsWith('/api/enhance') && r.request().method() === 'POST',
      { timeout: 100000 },
    );
    await page.getByTestId('enhance-button').click();
    const result = await responseWait;
    const body = await result.json();
    const elapsed = Number(((Date.now() - started) / 1000).toFixed(2));

    if (result.status() !== 200) {
      process.stdout.write(JSON.stringify({
        status: 'AI_FAILED',
        http_status: result.status(),
        elapsed_seconds: elapsed,
        error_category: String(body?.detail || 'unknown error').slice(0, 160),
      }) + '\n');
      process.exitCode = 1;
    } else {
      const changes = body.changes || [];
      const preview = page.getByTestId('resume-preview');
      const originalNamePresent = (await preview.textContent()).includes('陈晓明');
      let humanGateChecked = false;
      let appliedFirst = false;
      if (changes.length > 0) {
        await page.getByTestId('changes-list').waitFor({ state: 'visible', timeout: 8000 });
        const apply = page.getByRole('button', { name: '应用已批准的修改' });
        humanGateChecked = await apply.isDisabled();
        const suggestion = page.getByTestId('changes-list').locator('input[type="checkbox"]').first();
        await suggestion.check();
        await apply.click();
        await page.getByTestId('changes-list').waitFor({ state: 'visible' });
        appliedFirst = (await preview.textContent()).includes(changes[0].after);
      }
      await page.getByTestId('review-checkbox').check();
      const wordRequest = page.waitForEvent('download', { timeout: 60000 });
      await page.getByTestId('download-docx').click();
      const word = await wordRequest;
      const wordDownloaded = word.suggestedFilename().endsWith('.docx')
        && await word.failure() === null;
      const pdfRequest = page.waitForEvent('download', { timeout: 60000 });
      await page.getByTestId('download-pdf').click();
      const pdf = await pdfRequest;
      const pdfDownloaded = pdf.suggestedFilename().endsWith('.pdf')
        && await pdf.failure() === null;
      const ok = body.mode === 'ai' && originalNamePresent && wordDownloaded
        && pdfDownloaded && (changes.length === 0 || (humanGateChecked && appliedFirst));
      process.stdout.write(JSON.stringify({
        status: ok ? 'PASS' : 'CHECK_FAILED',
        http_status: result.status(),
        elapsed_seconds: elapsed,
        provider: 'DeepSeek',
        model: 'deepseek-flash',
        suggestions: changes.length,
        approval_gate_enforced: humanGateChecked,
        approved_edit_applied: appliedFirst,
        original_identity_preserved: originalNamePresent,
        docx_download: wordDownloaded,
        pdf_download: pdfDownloaded,
      }) + '\n');
      if (!ok) process.exitCode = 1;
    }
    await context.close();
  } catch (error) {
    process.stdout.write(JSON.stringify({
      status: 'BROWSER_FAILED',
      category: error?.name || 'Error',
      message: String(error?.message || '').slice(0, 160),
    }) + '\n');
    process.exitCode = 1;
  } finally {
    if (browser) await browser.close();
  }
}
