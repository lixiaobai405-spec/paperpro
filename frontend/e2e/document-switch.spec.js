import { test, expect } from '@playwright/test';

test('switching documents resets focused list drafts instead of leaking old resume skills', async ({ page }) => {
  await page.goto('/');
  await page.getByTestId('demo-button').click();
  const skills = page.getByRole('textbox', { name: '专业技能' });
  await expect(skills).toContainText('Python');

  let release;
  const intercepted = new Promise((resolve) => { release = resolve; });
  let allow;
  await page.route('**/api/extract', async (route) => {
    allow = () => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        filename: 'candidate-b.png', method: 'image-ocr', warnings: [],
        source_text: 'CANDIDATE B\n专业技能\nNEW-B',
        resume: {
          name: 'CANDIDATE B', title: 'Engineer', phone: '',
          email: '', location: '', links: [], summary: '',
          skills: ['NEW-B'], experience: [], projects: [], education: [],
          additional: ['Some resume content'],
        },
      }),
    });
    release();
  });
  await page.locator('input[type="file"]').first().setInputFiles({
    name: 'candidate-b.png', mimeType: 'image/png', buffer: Buffer.from('mock uploaded file'),
  });
  await intercepted;
  await skills.focus();
  await expect(skills).toHaveValue(/Python/);
  await allow();
  await expect(page.getByTestId('resume-preview')).toContainText('CANDIDATE B');
  const newSkills = page.getByRole('textbox', { name: '专业技能' });
  await expect(newSkills).toHaveValue('NEW-B');
  await newSkills.press('End');
  await newSkills.type('，Extra');
  await expect(newSkills).toHaveValue('NEW-B，Extra');
  await expect(page.getByTestId('resume-preview')).toContainText('NEW-B');
  await expect(page.getByTestId('resume-preview')).not.toContainText('Python');
});

test('changing target role during upload does not silently discard selected document', async ({ page }) => {
  await page.goto('/');
  await page.getByTestId('demo-button').click();
  await expect(page.getByTestId('resume-preview')).toContainText('陈晓明');

  let release;
  const intercepted = new Promise((resolve) => { release = resolve; });
  let allow;
  await page.route('**/api/extract', async (route) => {
    allow = () => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        filename: 'new-candidate.docx', method: 'docx', warnings: [],
        source_text: 'CANDIDATE B\n专业技能\nPython',
        resume: {
          name: 'CANDIDATE B', title: 'Engineer', phone: '',
          email: '', location: '', links: [], summary: 'New resume',
          skills: ['Python'], experience: [], projects: [], education: [], additional: [],
        },
      }),
    });
    release();
  });

  await page.locator('input[type="file"]').first().setInputFiles({
    name: 'new-candidate.docx',
    mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    buffer: Buffer.from('staged test upload'),
  });
  await intercepted;

  // Target role belongs to the AI request, not to the file identity.
  await page.getByRole('textbox', { name: '目标岗位（可选）' }).fill('新目标岗位');
  allow();
  await expect(page.getByTestId('resume-preview')).toContainText('CANDIDATE B', { timeout: 4000 });
  await expect(page.getByText('new-candidate.docx')).toBeVisible();
  await expect(page.getByRole('textbox', { name: '目标岗位（可选）' })).toHaveValue('新目标岗位');
});
