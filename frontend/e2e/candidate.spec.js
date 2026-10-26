import { test, expect, devices } from '@playwright/test';
import fs from 'node:fs/promises';

test('no explicit JD omits unrequested academic and optional requirements without changing computed score', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: '填入虚构演示资料' }).click();
  await page.getByTestId('candidate-parse-text').click();
  await page.getByTestId('candidate-next-target').click();
  await page.getByTestId('candidate-target-role').fill('后端开发工程师');
  const responsePromise = page.waitForResponse(response =>
    response.url().endsWith('/api/diagnosis/report') && response.request().method() === 'POST');
  await page.getByTestId('candidate-generate').click();
  const response = await responsePromise;
  expect(response.ok()).toBe(true);
  const match = (await response.json()).dimensions.match;
  const omitted = match.requirements.filter(row => row.status === '岗位未要求');
  expect(omitted.some(row => row.id === 'education')).toBe(true);
  expect(omitted.some(row => row.id === 'industry')).toBe(true);
  expect(omitted.some(row => row.id === 'leadership')).toBe(true);
  const table = page.getByTestId('requirements-table');
  await expect(table.locator('tbody tr')).toHaveCount(match.requirements.length - omitted.length);
  for (const row of omitted) {
    await expect(table.getByRole('row', { name: new RegExp(row.label) })).toHaveCount(0);
  }
  await expect(table.getByText('岗位未要求')).toHaveCount(0);
  await expect(page.getByTestId('dimension-match')).toContainText(String(match.score));
});

test('an explicit JD degree threshold keeps the academic requirement visible', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: '填入虚构演示资料' }).click();
  await page.getByTestId('candidate-parse-text').click();
  await page.getByTestId('candidate-next-target').click();
  await page.getByTestId('candidate-target-role').fill('后端开发工程师');
  await page.getByRole('textbox', { name: '目标岗位 JD（可选，但推荐）' })
    .fill('任职要求：硕士及以上学历，熟悉 Python 和 SQL。');
  const responsePromise = page.waitForResponse(response =>
    response.url().endsWith('/api/diagnosis/report') && response.request().method() === 'POST');
  await page.getByTestId('candidate-generate').click();
  const response = await responsePromise;
  expect(response.ok()).toBe(true);
  const match = (await response.json()).dimensions.match;
  const education = match.requirements.find(row => row.id === 'education');
  expect(education.status).not.toBe('岗位未要求');
  const table = page.getByTestId('requirements-table');
  await expect(table.getByRole('row', { name: /学历要求/ })).toBeVisible();
  await expect(table.getByRole('row', { name: /学历要求/ })).toContainText(education.status);
  await expect(table.locator('tbody tr')).toHaveCount(
    match.requirements.filter(row => row.status !== '岗位未要求').length);
});

test('candidate wizard: pasted resume, editable fields, target gate, five dimensions, selected-only downloads', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByTestId('candidate-app')).toBeVisible();
  await expect(page.getByTestId('wizard-steps')).toContainText('上传简历');
  await page.getByRole('button', { name: '填入虚构演示资料' }).click();
  await page.getByTestId('candidate-parse-text').click();
  await expect(page.getByTestId('candidate-name')).toHaveValue('陈晓明');
  const originalCompany = await page.getByTestId('experience-company-0').inputValue();
  await page.getByTestId('experience-company-0').fill('已核对的示例科技');
  await page.getByTestId('experience-start-0').fill('2022.05');
  await page.getByTestId('experience-role-0').fill('高级后端开发工程师');
  await page.getByTestId('candidate-next-target').click();
  const generate=page.getByTestId('candidate-generate');
  await expect(generate).toBeDisabled();
  await page.getByTestId('candidate-target-role').fill('后端开发工程师');
  await expect(generate).toBeEnabled();
  await generate.click();
  for (const section of ['match','experience','potential','motivation','verification']) {
    await expect(page.getByTestId('dimension-'+section)).toBeVisible();
  }
  const rowCount = await page.getByTestId('requirements-table').locator('tbody tr').count();
  expect(rowCount).toBeGreaterThanOrEqual(3);
  await expect(page.getByTestId('requirements-table').getByText('岗位未要求')).toHaveCount(0);
  await expect(page.getByText(/不是实际企业录用概率/)).toBeVisible();
  await page.getByTestId('candidate-next-todo').click();
  await page.getByTestId('candidate-more-advice').locator('summary').click();
  await expect(page.getByTestId('advice-advice-01')).toBeVisible();
  await expect(page.getByText('可选深化', { exact: true }).first()).toBeVisible();
  const checkboxes = page.getByTestId('advice-advice-01').locator('input[type="checkbox"]');
  await checkboxes.check();
  const firstTitle = await page.getByTestId('advice-advice-01').locator('strong').first().textContent();
  const downloadPromise = page.waitForEvent('download');
  await page.getByTestId('candidate-download-txt').click();
  const download = await downloadPromise;
  const content = (await fs.readFile(await download.path())).toString('utf8');
  expect(content).toContain('优化待办清单');
  expect(content).toContain(firstTitle);
  expect(content.match(/位置：/g)?.length).toBe(1);
  const pdfEvent=page.waitForEvent('download');
  await page.getByTestId('candidate-download-pdf').click();
  const pdf=await pdfEvent;
  const bytes=await fs.readFile(await pdf.path());
  expect(bytes.subarray(0,4).toString()).toBe('%PDF');
  await page.getByRole('button', { name: '返回诊断报告' }).click();
  await expect(page.getByTestId('dimension-match')).toBeVisible();
  await page.getByRole('button', { name: '返回修改目标' }).click();
  await expect(page.getByTestId('candidate-target-role')).toHaveValue('后端开发工程师');
  await page.getByRole('button', { name: '返回修改简历' }).click();
  await expect(page.getByTestId('experience-company-0')).toHaveValue('已核对的示例科技');
  await expect(page.getByTestId('experience-start-0')).toHaveValue('2022.05');
  expect(originalCompany).not.toBe('已核对的示例科技');
});

test('editing the target during diagnosis cannot accept a stale report or deadlock loading', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: '填入虚构演示资料' }).click();
  await page.getByTestId('candidate-parse-text').click();
  await page.getByTestId('candidate-next-target').click();
  await page.getByTestId('candidate-target-role').fill('后端开发工程师');

  let fulfillOld;
  let notifyRequest;
  const intercepted = new Promise(resolve => { notifyRequest = resolve; });
  await page.route('**/api/diagnosis/report', async route => {
    const backend = await route.fetch();
    fulfillOld = () => route.fulfill({ response: backend });
    notifyRequest();
  }, { times: 1 });

  await page.getByTestId('candidate-generate').click();
  await intercepted;
  await page.getByTestId('candidate-target-role').fill('数据分析师');
  await fulfillOld();

  await expect(page.getByTestId('candidate-target-role')).toHaveValue('数据分析师');
  await expect(page.getByTestId('dimension-match')).toHaveCount(0);
  await expect(page.getByTestId('candidate-generate')).toBeEnabled();
  await page.getByTestId('candidate-generate').click();
  await expect(page.getByTestId('dimension-match')).toBeVisible();
  await expect(page.getByText('岗位：数据分析师')).toBeVisible();
});

test('company-only target works and report dims can be independently disabled', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: '填入虚构演示资料' }).click();
  await page.getByTestId('candidate-parse-text').click();
  await page.getByTestId('candidate-next-target').click();
  await page.getByTestId('candidate-target-company').fill('示例单位');
  await page.getByRole('checkbox', { name: '学习能力与发展潜力' }).uncheck();
  await page.getByTestId('candidate-generate').click();
  await expect(page.getByTestId('dimension-potential')).toContainText('已关闭');
  await expect(page.getByTestId('dimension-match')).toContainText('仅提供公司名称');
  await expect(page.getByTestId('dimension-verification')).toBeVisible();
});

test('mobile viewport keeps upload and report reachable with no horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.getByTestId('candidate-dropzone')).toBeVisible();
  await page.getByRole('button', { name: '填入虚构演示资料' }).click();
  await page.getByTestId('candidate-parse-text').click();
  await page.getByTestId('candidate-next-target').click();
  await page.getByTestId('candidate-target-role').fill('产品经理');
  await page.getByTestId('candidate-generate').click();
  await expect(page.getByTestId('dimension-match')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
});

test('paste parsing can be delayed more than 10 seconds with visible wait feedback', async ({ page }) => {
  await page.clock.install();
  await page.goto('/');
  await page.getByRole('button', { name: '填入虚构演示资料' }).click();
  let unblock;
  let arrive;
  const started = new Promise(resolve => { arrive=resolve; });
  await page.route('**/api/diagnosis/paste', async route => {
    unblock=()=>route.fulfill({status:422,contentType:'application/json',body:'{"detail":"模拟超时错误，未解析"}'});
    arrive();
  });
  await page.getByTestId('candidate-parse-text').click();
  await started;
  await page.clock.fastForward('11:00'); // advance virtual time; no 11-minute real wait
  await expect(page.getByText(/已超过 10 秒/)).toBeVisible();
  unblock();
  await expect(page.getByText(/模拟超时错误/)).toBeVisible();
});

test('changing pasted source during parsing must reject the old result', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: '填入虚构演示资料' }).click();
  let allowOld, seenRequest;
  const intercepted=new Promise(resolve=>{seenRequest=resolve;});
  await page.route('**/api/diagnosis/paste',async route=>{
    const response=await route.fetch();
    allowOld=()=>route.fulfill({response});
    seenRequest();
  }, {times:1});
  await page.getByTestId('candidate-parse-text').click();
  await intercepted;
  const changed='替代候选人\n专业技能\nPython';
  await page.getByTestId('candidate-paste').fill(changed);
  await allowOld();
  await expect(page.getByTestId('candidate-paste')).toHaveValue(changed);
  await expect(page.getByTestId('candidate-name')).toHaveCount(0);
  await expect(page.getByTestId('candidate-parse-text')).toBeEnabled();
  await page.getByTestId('candidate-parse-text').click();
  await expect(page.getByTestId('candidate-name')).toHaveValue('替代候选人');
});

test('repeated section toggles in StrictMode do not lose checkbox state', async ({ page }) => {
  const pageErrors=[];
  page.on('pageerror',error=>pageErrors.push(error.message));
  await page.goto('/');
  await page.getByRole('button', { name: '填入虚构演示资料' }).click();
  await page.getByTestId('candidate-parse-text').click();
  await page.getByTestId('candidate-next-target').click();
  const potential=page.getByRole('checkbox', { name: '学习能力与发展潜力' });
  await potential.uncheck();
  await expect(potential).not.toBeChecked();
  await potential.check();
  await expect(potential).toBeChecked();
  await page.getByTestId('candidate-target-role').fill('后端开发工程师');
  await page.getByTestId('candidate-generate').click();
  await expect(page.getByTestId('dimension-potential')).toContainText('已生成');
  expect(pageErrors).toEqual([]);
});

test('emulated Android/iOS file inputs support photo picker submission', async ({ browser }) => {
  // This covers responsive HTML file-picker wiring, not native hardware
  // gallery/camera permission dialogs, which require physical device QA.
  for (const deviceName of ['Pixel 7', 'iPhone 13']) {
    const { defaultBrowserType: _browserType, ...device } = devices[deviceName];
    const context = await browser.newContext(device);
    try {
      const mobile = await context.newPage();
      await mobile.goto('/');
      const field = mobile.getByTestId('candidate-dropzone').locator('input[type="file"]');
      await expect(field).toHaveCount(1);
      const accepted = await field.getAttribute('accept');
      expect(accepted).toContain('image/png');
      expect(accepted).toContain('image/jpeg');
      let uploaded = false;
      await mobile.route('**/api/diagnosis/parse', async route => {
        uploaded = route.request().headers()['content-type'].includes('multipart/form-data');
        const draft = {
          name: '纯合成照片候选人', title: '工程师',
          phone: '', email: '', location: '', links: [],
          summary: '', self_evaluation: '', skills: ['Python'],
          experience: [], education: [], projects: [],
          certificates: [], additional: [], source_sha256: 'sample',
          source_text: '纯合成图像，仅验证浏览器文件选择事件',
        };
        await route.fulfill({
          status: 200, contentType: 'application/json',
          body: JSON.stringify({
            status: 'ok', filename: 'photo.png', method: 'image-ocr',
            sha256: 'sample', resume: draft, warnings: ['照片识别请人工校对'],
          }),
        });
      });
      await field.setInputFiles({
        name: 'photo.png',
        mimeType: 'image/png',
        buffer: Buffer.from(
          'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAObXG1QAAAAASUVORK5CYII=',
          'base64',
        ),
      });
      await expect(mobile.getByTestId('candidate-name')).toHaveValue('纯合成照片候选人');
      await expect(mobile.getByText('照片识别请人工校对')).toBeVisible();
      expect(uploaded).toBe(true);
      expect(await mobile.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
    } finally {
      await context.close();
    }
  }
});

test('actual Chrome scan upload runs real local OCR and opens editable review', async ({ page }) => {
  await page.goto('/');
  // Build a readable, fully synthetic screenshot inside browser memory.
  // The request below is NOT mocked: it reaches the real FastAPI /parse + OCR.
  const image64 = await page.evaluate(() => {
    const canvas = document.createElement('canvas');
    canvas.width = 2100;
    canvas.height = 1050;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, 2100, 1050);
    ctx.fillStyle = '#111111';
    ctx.font = '52px Arial';
    const rows = [
      'ALEX EXAMPLE',
      'Target Role: Backend Developer',
      'Skills',
      'Python, SQL, Docker',
      'Work Experience',
      '2022.01 - 2025.06 Example Labs | Backend Developer',
      '- Built Python SQL APIs',
      'Education',
      'Example University | Bachelor',
    ];
    rows.forEach((line, i) => ctx.fillText(line, 70, 100 + 94 * i));
    return canvas.toDataURL('image/png').split(',')[1];
  });
  const sent = page.waitForResponse(response =>
    response.url().endsWith('/api/diagnosis/parse') &&
    response.request().method() === 'POST', { timeout: 120000 });
  await page.getByTestId('candidate-dropzone').locator('input[type=file]').setInputFiles({
    name: 'synthetic-scan.png', mimeType: 'image/png',
    buffer: Buffer.from(image64, 'base64'),
  });
  const response = await sent;
  expect(response.status()).toBe(200);
  expect((await response.json()).method).toBe('image-ocr');
  await expect(page.getByTestId('candidate-name')).toHaveValue('ALEX EXAMPLE');
  await expect(page.getByText('synthetic-scan.png')).toBeVisible();
  await page.getByTestId('candidate-next-target').click();
  await page.getByTestId('candidate-target-role').fill('Backend Developer');
  await page.getByTestId('candidate-generate').click();
  await expect(page.getByTestId('dimension-match')).toBeVisible();
});

test('selected diagnosis advice hands off reviewed facts to classic exactly once, without auto-approval', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: '填入虚构演示资料' }).click();
  await page.getByTestId('candidate-parse-text').click();
  await page.getByTestId('candidate-name').fill('陈测试');
  await page.getByTestId('experience-company-0').fill('已核对星海科技');
  await page.getByTestId('experience-role-0').fill('高级后端工程师');
  await page.getByLabel('原始经历标题（用于溯源）').fill('2022.07–2025.06 星辰科技｜平台组（借调）｜后端工程师');
  await page.getByTestId('experience-start-0').fill('2021.04');
  await page.getByTestId('candidate-next-target').click();
  await page.getByTestId('candidate-target-role').fill('Python 后端工程师');
  await page.getByLabel('目标岗位 JD（可选，但推荐）').fill('负责 Python API、SQL 数据库与 Docker 部署。');
  await page.getByTestId('candidate-generate').click();
  await page.getByTestId('candidate-next-todo').click();
  await page.getByTestId('candidate-more-advice').locator('summary').click();
  await page.getByTestId('advice-advice-01').locator('input[type=checkbox]').check();
  let unexpectedAiRequests = 0;
  page.on('request', request => {
    if (request.url().includes('/api/enhance')) unexpectedAiRequests += 1;
  });
  await page.getByTestId('candidate-open-classic').click();
  await expect(page).toHaveURL(/\/classic$/);
  await expect(page.getByTestId('field-name')).toHaveValue('陈测试');
  await expect(page.getByTestId('handoff-advice')).toContainText('岗位定位不明确');
  await expect(page.getByTestId('handoff-advice')).toContainText('advice-01');
  const comparison = page.getByTestId('handoff-heading-comparison-0');
  await expect(comparison).toContainText('平台组（借调）');
  await expect(comparison).toContainText('已核对星海科技');
  await expect(comparison).toContainText('高级后端工程师');
  await expect(page.getByLabel('目标岗位（可选）')).toHaveValue('Python 后端工程师');
  await expect(page.getByLabel('岗位描述（可选）')).toHaveValue('负责 Python API、SQL 数据库与 Docker 部署。');
  const preview = page.getByTestId('resume-preview');
  await expect(preview).toContainText('已核对星海科技');
  await expect(preview).toContainText('高级后端工程师');
  await expect(preview).toContainText('2021.04');
  await expect(preview).not.toContainText('平台组（借调）');
  const previewText = await preview.innerText();
  expect((previewText.match(/CET-6/g) || []).length).toBe(1);
  expect((previewText.match(/拥有3年后端系统开发经验/g) || []).length).toBe(1);
  await expect(page.getByTestId('review-checkbox')).not.toBeChecked();
  await expect(page.getByTestId('download-docx')).toBeDisabled();
  expect(unexpectedAiRequests).toBe(0);
  await page.getByTestId('review-checkbox').check();
  const workTitleField = page.getByTestId('editor-panel')
    .getByLabel('机构、角色及起止时间').first();
  await workTitleField.fill((await workTitleField.inputValue()) + ' · 平台组（借调）');
  await expect(comparison).toContainText('平台组（借调）');
  await expect(preview).toContainText('平台组（借调）');
  await expect(page.getByTestId('review-checkbox')).not.toBeChecked();
  await expect(page.getByTestId('download-docx')).toBeDisabled();
  await page.getByTestId('review-checkbox').check();
  await expect(page.getByTestId('download-docx')).toBeEnabled();
  const exportRequest = page.waitForRequest(request =>
    request.url().includes('/api/export?format=docx') && request.method() === 'POST'
  );
  const exportDownload = page.waitForEvent('download');
  await page.getByTestId('download-docx').click();
  const submitted = (await exportRequest).postDataJSON().resume;
  expect(submitted.experience[0].heading).toContain('已核对星海科技');
  expect(submitted.experience[0].heading).toContain('高级后端工程师');
  expect(submitted.experience[0].heading).toContain('2021.04');
  expect(submitted.experience[0].heading).toContain('平台组（借调）');
  const downloaded = await exportDownload;
  const docxBytes = await fs.readFile(await downloaded.path());
  expect(docxBytes.subarray(0, 2).toString()).toBe('PK');
  await page.reload();
  await expect(page.getByTestId('handoff-advice')).toHaveCount(0);
  await expect(page.getByTestId('field-name')).toHaveCount(0);
});


test('removing a transferred job keeps original-title comparisons with the right remaining job', async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('paperpro-candidate-to-classic-v1', JSON.stringify({
      version: 1, createdAt: Date.now(),
      resume: {
        name: '虚构测试人', title: '软件开发', email: '', phone: '',
        location: '', links: [], summary: '', skills: [],
        experience: [
          { heading: '2020.01 — 2021.01  甲公司 ｜ 工程师', bullets: [] },
          { heading: '2021.02 — 2022.02  乙公司 ｜ 分析师', bullets: [] },
        ],
        projects: [], education: [], additional: [],
      },
      advice: [],
      headingComparisons: [
        { index: 0, original: '甲公司｜平台部门（原始）', projected: '甲公司 ｜ 工程师' },
        { index: 1, original: '乙公司｜海外协作（原始）', projected: '乙公司 ｜ 分析师' },
      ],
    }));
  });
  await page.goto('/classic');
  await expect(page.getByTestId('handoff-heading-comparison-0')).toContainText('平台部门（原始）');
  await expect(page.getByTestId('handoff-heading-comparison-1')).toContainText('海外协作（原始）');
  await page.getByTestId('工作经历').getByRole('button', {name: '删除此条'}).first().click();
  await expect(page.getByTestId('handoff-heading-comparison-1')).toHaveCount(0);
  await expect(page.getByTestId('handoff-heading-comparison-0')).toContainText('海外协作（原始）');
  await expect(page.getByTestId('handoff-heading-comparison-0')).not.toContainText('平台部门（原始）');
  await expect(page.getByTestId('resume-preview')).toContainText('乙公司');
  await expect(page.getByTestId('resume-preview')).not.toContainText('甲公司');
  await expect(page.getByTestId('download-docx')).toBeDisabled();
});


test('deleting a reviewed entry shifts its source heading comparison without misattribution', async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('paperpro-candidate-to-classic-v1', JSON.stringify({
      version: 1, createdAt: Date.now(),
      resume: {
        name: '模拟求职者', title: '后端工程师', email: '', phone: '',
        location: '', links: [], summary: '', skills: [],
        education: [], projects: [], additional: [],
        experience: [
          { heading: '2021.01 — 2022.12 甲公司 ｜ 开发', bullets: [] },
          { heading: '2023.01 — 2024.12 乙公司 ｜ 运维', bullets: [] },
        ],
      },
      targetRole: '后端工程师', jobDescription: '', advice: [],
      headingComparisons: [
        { index: 0, original: '甲公司 - 开发 - 甲项目部', projected: '2021.01 — 2022.12 甲公司 ｜ 开发' },
        { index: 1, original: '乙公司 - 运维 - 乙平台组', projected: '2023.01 — 2024.12 乙公司 ｜ 运维' },
      ],
    }));
  });
  await page.goto('/classic');
  await expect(page.getByTestId('handoff-heading-comparison-0')).toContainText('甲项目部');
  await expect(page.getByTestId('handoff-heading-comparison-1')).toContainText('乙平台组');
  await page.getByTestId('工作经历').getByRole('button', { name: '删除此条' }).first().click();
  await expect(page.getByTestId('handoff-heading-comparison-1')).toHaveCount(0);
  await expect(page.getByTestId('handoff-heading-comparison-0')).toContainText('乙平台组');
  await expect(page.getByTestId('handoff-heading-comparison-0')).not.toContainText('甲项目部');
  await expect(page.getByTestId('resume-preview')).not.toContainText('甲公司');
  await expect(page.getByTestId('resume-preview')).toContainText('乙公司');
});


test('stale or malformed one-shot handoff cannot prefill the classic editor', async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('paperpro-candidate-to-classic-v1', JSON.stringify({
      version: 1, createdAt: Date.now() - 31 * 60 * 1000,
      resume: { name: '过期候选人', experience: [] }, advice: [],
    }));
  });
  await page.goto('/classic');
  await expect(page.getByTestId('demo-button')).toBeVisible();
  await expect(page.getByTestId('field-name')).toHaveCount(0);
  await expect(page.getByTestId('handoff-advice')).toHaveCount(0);
  expect(await page.evaluate(() => sessionStorage.getItem('paperpro-candidate-to-classic-v1'))).toBeNull();
});


test('legacy resume editor remains available on /classic', async ({ page }) => {
  await page.goto('/classic');
  await expect(page.getByTestId('demo-button')).toBeVisible();
});


test('AI interpretation is opt-in and cannot run without explicit consent', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: '填入虚构演示资料' }).click();
  await page.getByTestId('candidate-parse-text').click();
  await page.getByTestId('candidate-next-target').click();
  await page.getByTestId('candidate-target-role').fill('后端开发工程师');
  const useAi=page.getByRole('checkbox', { name: /使用 DeepSeek 为已计算的时间线/ });
  await useAi.check();
  const run=page.getByTestId('candidate-generate');
  await expect(run).toBeDisabled();
  await page.getByTestId('candidate-ai-key').fill('SYNTHETIC_TEST_KEY');
  await page.getByTestId('candidate-ai-consent').check();
  let externalCallWasRequested=false;
  await page.route('**/api/diagnosis/report', async (route) => {
    const request=route.request().postDataJSON();
    externalCallWasRequested=request.use_ai && request.ai_consent
      && request.ai_provider==='deepseek';
    const safe={...request,use_ai:false,ai_consent:false,api_key:undefined};
    const backend=await route.fetch({postData:JSON.stringify(safe)});
    const result=await backend.json();
    result.meta.ai_narrative='completed';
    result.meta.ai_notice='AI 为固定时间线提供了辅助解释。';
    result.dimensions.experience.ai_commentary='仅依据已计算的数据提供解释，不重新计算时间。';
    await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(result)});
  });
  await run.click();
  await expect(page.getByTestId('dimension-experience')).toContainText('DeepSeek 辅助解读');
  expect(externalCallWasRequested).toBe(true);
});


test('PDF work-role suggestions remain unscored until human accepts, and can be ignored', async ({ page }) => {
  await page.goto('/');
  const heading0 = '2021.07-2023.12 虚构技术有限公司 平台运营';
  const heading1 = '2023.12-2024.09 合成软件有限公司 业务分析';
  const initial = {
    name: '合成人员', title: '', email: '', phone: '', location: '',
    links: [], summary: '', self_evaluation: '', skills: [],
    certificates: [], education: [], projects: [], additional: [],
    source_sha256: 'synthetic',
    source_text: heading0 + '\n' + heading1,
    experience: [
      {heading:heading0,company:'虚构技术有限公司 平台运营',role:'',
       start_date:'2021.07',end_date:'2023.12',bullets:[]},
      {heading:heading1,company:'合成软件有限公司 业务分析',role:'',
       start_date:'2023.12',end_date:'2024.09',bullets:[]},
    ],
  };
  const hints = [
    {id:'work-relation-0',experience_index:0,source_path:'experience.0.heading',
     source_heading:heading0,suggested_company:'虚构技术有限公司',
     suggested_role:'平台运营',status:'unverified',note:'未经核实的候选',
     evidence:{page_index:0,page_number:1,source_kind:'native_pdf_text',
       boxes:{date:[.07,.25,.27,.27],employer:[.3,.25,.59,.27],role:[.68,.25,.84,.27]}},
     confidence:{tier:'low',calibrated:false,semantic_check:'not_verified',
       signals:['horizontal_alignment','existing_dated_experience'],
       missing:['independent_role_confirmation']}},
    {id:'work-relation-1',experience_index:1,source_path:'experience.1.heading',
     source_heading:heading1,suggested_company:'合成软件有限公司',
     suggested_role:'业务分析',status:'unverified',note:'未经核实的候选',
     evidence:{page_index:1,page_number:2,source_kind:'native_pdf_text',
       boxes:{date:[.07,.25,.27,.27],employer:[.3,.25,.59,.27],role:[.68,.25,.84,.27]}},
     confidence:{tier:'low',calibrated:false,semantic_check:'not_verified',
       signals:['horizontal_alignment','existing_dated_experience'],
       missing:['independent_role_confirmation']}},
  ];
  await page.route('**/api/diagnosis/parse', async route =>
    route.fulfill({
      status:200, contentType:'application/json',
      body:JSON.stringify({
        status:'ok',filename:'mock-work.pdf',method:'pdf-text',
        sha256:'synthetic',resume:initial,source_text:initial.source_text,
        warnings:['未经核实的工作职位排版候选'],review_hints:hints,
      }),
    })
  );
  await page.getByTestId('candidate-dropzone').locator('input[type=file]').setInputFiles({
    name:'mock-work.pdf',mimeType:'application/pdf',
    buffer:Buffer.from('%PDF-1.4\n% synthetic fixture\n'),
  });
  await expect(page.getByTestId('candidate-work-hints')).toBeVisible();
  await expect(page.getByTestId('work-hint-work-relation-0')).toContainText('低置信度 · 未经校准');
  await expect(page.getByTestId('work-hint-work-relation-0')).toContainText('PDF 第 1 页');
  await expect(page.getByTestId('work-hint-work-relation-0')).toContainText('职位文字块定位');
  await expect(page.getByTestId('work-hint-work-relation-1')).toContainText('PDF 第 2 页');
  await expect(page.getByTestId('experience-role-0')).toHaveValue('');
  await expect(page.getByTestId('experience-company-0')).toHaveValue(
    '虚构技术有限公司 平台运营'
  );
  await page.getByTestId('accept-work-relation-0').click();
  await expect(page.getByTestId('experience-role-0')).toHaveValue('平台运营');
  await expect(page.getByTestId('experience-company-0')).toHaveValue('虚构技术有限公司');
  await expect(page.getByTestId('experience-role-1')).toHaveValue('');
  await page.getByTestId('ignore-work-relation-1').click();
  await expect(page.getByTestId('candidate-work-hints')).toHaveCount(0);
  await expect(page.getByTestId('experience-role-1')).toHaveValue('');
  await page.getByTestId('candidate-next-target').click();
  await page.getByTestId('candidate-target-role').fill('平台运营');
  await page.getByTestId('candidate-generate').click();
  await expect(page.getByTestId('dimension-match')).toBeVisible();
});
