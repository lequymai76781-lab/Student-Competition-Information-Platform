import assert from 'node:assert/strict';
import { after, before, test } from 'node:test';
import { chromium, mount } from './browser-harness.mjs';

let browser;
before(async () => { browser = await chromium.launch({ headless: true, channel: 'msedge' }); });
after(async () => { await browser?.close(); });

test('deadline correction submits an explicit Shanghai datetime and keeps the edition target', async () => {
  let submitted;
  const page = await mount(browser, 'src/components/v09/CorrectionForm.tsx', 'CorrectionForm',
    { competitionId: 1, editionId: 7 }, (url, request) => {
      if (url.pathname.endsWith('/corrections')) submitted = request.postDataJSON();
      return { data: { id: 1, status: 'pending', field_review_id: 10 } };
    });
  await page.getByLabel('建议报名截止时间（北京时间，可选）').fill('2026-10-30T23:59');
  await page.getByLabel('具体说明').fill('官网通知延期到十月三十日');
  await page.getByRole('button', { name: '提交纠错', exact: true }).click();
  await page.getByText(/已提交，记录编号/).waitFor();
  assert.equal(submitted.competition_edition_id, 7);
  assert.equal(submitted.proposed_value, '2026-10-30T23:59:00+08:00');
  await page.close();
});

test('switching correction type discards an incompatible structured value', async () => {
  let submitted;
  const page = await mount(browser, 'src/components/v09/CorrectionForm.tsx', 'CorrectionForm',
    { competitionId: 1, editionId: 7 }, (url, request) => {
      submitted = request.postDataJSON();
      return { data: { id: 1, status: 'pending' } };
    });
  await page.getByLabel('建议报名截止时间（北京时间，可选）').fill('2026-10-30T23:59');
  await page.getByLabel('信息类型').selectOption('主办方错误');
  assert.equal(await page.getByLabel('建议正确值（可选）').inputValue(), '');
  await page.getByLabel('建议正确值（可选）').fill('核验后的测试主办方');
  await page.getByLabel('具体说明').fill('官网列出的主办方不同');
  await page.getByRole('button', { name: '提交纠错', exact: true }).click();
  await page.getByText(/已提交，记录编号/).waitFor();
  assert.equal(submitted.proposed_value, '核验后的测试主办方');
  await page.close();
});
