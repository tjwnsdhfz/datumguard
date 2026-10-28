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

test('restores an imported project without demo-specific IDs or room counts', async ({page}) => {
  await page.goto('/');
  const draft = {
    presetId: 'architecture-studio', projectName: 'Custom drawing', revision: 'B', snap: 50,
    grids: [], walls: [{id:'custom-wall',start:[0,0],end:[2000,0],thickness:100,wall_type:'interior'}],
    openings: [], columns: [], roomSeeds: [],
  };
  await page.getByLabel('작업 파일 선택', {exact:true}).setInputFiles({
    name: 'custom.json', mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify({format:'datumguard-architecture',version:1,draft})),
  });
  await page.getByRole('button', {name:'이 작업 열기',exact:true}).click();
  // Wait for the actual persisted input, not a fixed debounce delay.
  await expect.poll(() => page.evaluate(async () => {
    const database = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open('datumguard', 2);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    const saved = await new Promise<{value?: {projectName?: string}}>((resolve, reject) => {
      const request = database.transaction('drafts').objectStore('drafts').get('architecture-contract-draft-v1');
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    database.close();
    return saved?.value?.projectName;
  })).toBe('Custom drawing');
  await page.reload();
  await expect(page.getByLabel('프로젝트 이름', {exact:true})).toHaveValue('Custom drawing');
  await expect(page.getByRole('button', {name:'custom-wall',exact:true})).toBeVisible();
  await expect(page.getByTestId('architecture-download')).toBeDisabled();
});

test('invalidates evidence during drag and history navigation', async ({page}) => {
  await page.route('**/api/v1/architecture/designs/run', route => route.fulfill({
    json: {
      status:'passed', contract_hash:`sha256:${'a'.repeat(64)}`, artifact_hash:`sha256:${'b'.repeat(64)}`,
      measurements:[], violations:[], evidence:[], preview_svg:'', bundle_base64:'cGFzcw==', summary:{},
      timeline:[{stage:'contract_validation',status:'ready'},{stage:'official_bundle',status:'created'}],
    },
  }));
  await page.goto('/');
  await page.getByTestId('architecture-preset-studio').click();
  const run = page.getByTestId('architecture-run-verification');
  const download = page.getByTestId('architecture-download');
  await expect(run).toBeEnabled({timeout:75000});
  await run.click();
  await expect(download).toBeEnabled();
  const column = page.getByTestId('architecture-draggable-column');
  await column.scrollIntoViewIfNeeded();
  const bounds = (await column.boundingBox())!;
  await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + bounds.height / 2);
  await page.mouse.down();
  await page.mouse.move(bounds.x + bounds.width / 2 + 30, bounds.y + bounds.height / 2, {steps:5});
  // Evidence must disappear before pointer-up commits the history entry.
  await expect(download).toBeDisabled();
  await expect(page.getByTestId('architecture-contract-hash')).toHaveText('sha256:pending');
  await page.mouse.up();
  await run.click();
  await expect(download).toBeEnabled();
  await page.getByTestId('architecture-undo').click();
  await expect(page.getByTestId('architecture-timeline-approved')).toContainText('waiting');
  await expect(page.getByTestId('architecture-contract-hash')).toHaveText('sha256:pending');
  await run.click();
  await expect(download).toBeEnabled();
  await page.getByTestId('architecture-redo').click();
  await expect(page.getByTestId('architecture-artifact-hash')).toHaveText('sha256:pending');
  await expect(download).toBeDisabled();
});

test('maps a letterboxed SVG drag to exact model millimetres', async ({page}) => {
  await page.goto('/');
  await page.getByTestId('architecture-preset-studio').click();
  // A deliberately wide canvas leaves horizontal letterboxing under xMidYMid meet.
  await page.addStyleTag({content:'svg.arch-canvas { width:100%; height:240px !important; min-height:240px !important; aspect-ratio:auto !important; }'});
  const canvas = page.getByTestId('architecture-canvas');
  await canvas.scrollIntoViewIfNeeded();
  const screen = await canvas.evaluate((node: SVGSVGElement) => {
    const matrix = node.getScreenCTM()!;
    const point = node.createSVGPoint(); point.x = 4000; point.y = 4000;
    const start = point.matrixTransform(matrix);
    point.x = 4500;
    const end = point.matrixTransform(matrix);
    const bounds = node.getBoundingClientRect();
    return {start:{x:start.x,y:start.y}, end:{x:end.x,y:end.y}, scale:matrix.a, naive:bounds.width/node.viewBox.baseVal.width};
  });
  expect(Math.abs(screen.scale - screen.naive)).toBeGreaterThan(0.005);
  await page.mouse.move(screen.start.x, screen.start.y);
  await page.mouse.down();
  await page.mouse.move(screen.end.x, screen.end.y, {steps:5});
  await page.mouse.up();
  await expect(page.getByTestId('architecture-inspector-center-x')).toHaveValue('4500');
  await expect(page.getByTestId('architecture-inspector-center-y')).toHaveValue('4000');
});
