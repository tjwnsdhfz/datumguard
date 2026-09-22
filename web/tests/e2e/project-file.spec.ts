import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';

test('save, validate, preview, reopen and undo a personal architecture project', async ({page}) => {
  await page.goto('/');
  const name = page.getByLabel('프로젝트 이름', {exact:true});
  await name.fill('내 작업 왕복 검증');
  const downloadEvent = page.waitForEvent('download');
  await page.getByRole('button',{name:'작업 파일 저장',exact:true}).click();
  const download = await downloadEvent;
  const file = JSON.parse(await readFile((await download.path())!, 'utf8'));
  expect(file.draft.projectName).toBe('내 작업 왕복 검증');
  expect(file).not.toHaveProperty('result');
  file.draft.projectName = '불러온 수정본';
  await page.getByLabel('작업 파일 선택',{exact:true}).setInputFiles({name:'project.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(file))});
  await expect(page.getByRole('button',{name:'이 작업 열기',exact:true})).toBeVisible();
  await expect(name).toHaveValue('내 작업 왕복 검증');
  await page.getByRole('button',{name:'이 작업 열기',exact:true}).click();
  await expect(name).toHaveValue('불러온 수정본');
  await expect(page.getByTestId('architecture-download')).toBeDisabled();
  await page.getByTestId('architecture-undo').click();
  await expect(name).toHaveValue('내 작업 왕복 검증');
  await page.getByLabel('작업 파일 선택',{exact:true}).setInputFiles({name:'bad.json',mimeType:'application/json',buffer:Buffer.from('{}')});
  await expect(page.getByRole('alert').filter({hasText:'현재 작업은 유지됩니다'})).toBeVisible();
  await expect(name).toHaveValue('내 작업 왕복 검증');
  await page.setViewportSize({width:375,height:812});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('a late verification response cannot approve changed inputs', async ({page}) => {
  let release!: () => void;
  let intercepted!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  const started = new Promise<void>(resolve => { intercepted = resolve; });
  await page.route('**/api/v1/architecture/designs/run', async route => {
    const response = await route.fetch(); intercepted(); await held; await route.fulfill({response});
  });
  await page.goto('/');
  await expect(page.getByTestId('architecture-run-verification')).toBeEnabled({timeout:75000});
  await page.getByTestId('architecture-run-verification').click();
  await started;
  await page.getByLabel('프로젝트 이름',{exact:true}).fill('검증 중 변경한 작업');
  const responseArrived = page.waitForResponse('**/api/v1/architecture/designs/run');
  release(); await responseArrived;
  await expect(page.getByTestId('architecture-demo')).toHaveAttribute('data-verification-status','idle');
  await expect(page.getByTestId('architecture-download')).toBeDisabled();
});
