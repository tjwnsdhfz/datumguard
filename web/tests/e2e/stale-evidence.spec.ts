import { expect, test, type Page } from '@playwright/test';

const passed = {
  status:'passed', contract_hash:`sha256:${'a'.repeat(64)}`, artifact_hash:`sha256:${'b'.repeat(64)}`,
  measurements:[], violations:[], evidence:[], summary:{}, timeline:[], preview_svg:'',
  preview_mesh:null, step_base64:'cGFzcw==', bundle_base64:'cGFzcw==',
};

async function ready(page: Page) {
  await page.route('**/api/v1/ready', route => route.fulfill({json:{status:'ready',version:'test'}}));
  await page.route('**/api/v1/domains', route => route.fulfill({json:[
    {id:'architecture'}, {id:'mechanical_ship_plate'}, {id:'solid_part'}, {id:'plant_piping'},
  ]}));
}

const cases = [
  {name:'plate', path:'/plate', draftKey:'current-contract-draft', endpoint:'**/api/v1/designs/run?auto_repair=true',
    run:(page:Page) => page.getByRole('button',{name:/DXF 생성 및 독립 검증/}),
    edit:(page:Page) => page.getByLabel('프로젝트 이름'),
    approved:(page:Page) => page.getByRole('button',{name:/검증 ZIP 받기/})},
  {name:'solid', path:'/solid', draftKey:'solid-contract-draft-v1', endpoint:'**/api/v1/solid/designs/run',
    run:(page:Page) => page.getByTestId('solid-run-button'),
    edit:(page:Page) => page.getByLabel('Project',{exact:true}),
    approved:(page:Page) => page.getByTestId('solid-download-bundle')},
  {name:'piping', path:'/piping', draftKey:'piping-contract-draft-v1', endpoint:'**/api/v1/piping/designs/run',
    run:(page:Page) => page.getByTestId('piping-run-verification'),
    edit:(page:Page) => page.locator('#piping-valve-offset'),
    approved:(page:Page) => page.getByTestId('piping-download')},
];

for (const scenario of cases) {
  test(`${scenario.name} cannot approve edited inputs from a late response`, async ({page}) => {
    await ready(page);
    let release!: () => void;
    let started!: () => void;
    const pending = new Promise<void>(resolve => { release = resolve; });
    const intercepted = new Promise<void>(resolve => { started = resolve; });
    await page.route(scenario.endpoint, async route => {
      started(); await pending; await route.fulfill({json:passed});
    });
    await page.goto(scenario.path);
    await expect(scenario.run(page)).toBeEnabled();
    await scenario.run(page).click();
    await intercepted;
    await scenario.edit(page).fill(scenario.name === 'piping' ? '2400' : 'Changed during verification');
    const arrived = page.waitForResponse(scenario.endpoint);
    release(); await (await arrived).finished();
    // Let response handling and React's next paint settle before asserting absence.
    await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
    await expect(scenario.run(page)).toBeEnabled();
    await expect(page.getByText(passed.contract_hash, {exact:true})).toHaveCount(0);
    if (scenario.name === 'piping') await expect(scenario.approved(page)).toBeDisabled();
    else await expect(scenario.approved(page)).toHaveCount(0);
  });

  test(`${scenario.name} invalidates an approved bundle as soon as input changes`, async ({page}) => {
    await ready(page);
    await page.route(scenario.endpoint, route => route.fulfill({json:passed}));
    await page.goto(scenario.path);
    await expect(scenario.run(page)).toBeEnabled();
    await scenario.run(page).click();
    await expect(scenario.approved(page)).toBeEnabled();
    await scenario.edit(page).fill(scenario.name === 'piping' ? '2500' : 'Changed after verification');
    await expect(page.getByText(passed.contract_hash, {exact:true})).toHaveCount(0);
    if (scenario.name === 'piping') await expect(scenario.approved(page)).toBeDisabled();
    else await expect(scenario.approved(page)).toHaveCount(0);
  });

  test(`${scenario.name} ignores a delayed saved draft after edits and verification`, async ({page}) => {
    await ready(page);
    await page.route(scenario.endpoint, route => route.fulfill({json:passed}));
    await page.goto(scenario.path);
    const oldValue = scenario.name === 'piping' ? '2200' : 'Previously saved project';
    const newValue = scenario.name === 'piping' ? '2600' : 'New work must survive';
    await scenario.edit(page).fill(oldValue);
    await expect.poll(() => page.evaluate(async ({key, name}) => {
      const database = await new Promise<IDBDatabase>((resolve, reject) => {
        const request = indexedDB.open('datumguard', 2);
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
      const saved = await new Promise<{value?: {projectName?: string; inlineComponents?: {id:string;offset:number}[]}}>((resolve, reject) => {
        const request = database.transaction('drafts').objectStore('drafts').get(key);
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
      database.close();
      return name === 'piping'
        ? String(saved?.value?.inlineComponents?.find(item => item.id === 'valve-1')?.offset)
        : saved?.value?.projectName;
    }, {key:scenario.draftKey, name:scenario.name})).toBe(oldValue);

    // Hold the real IndexedDB transaction's completion callback, not a timing guess.
    await page.addInitScript((key) => {
      const state = {pending:[] as (() => void)[], release:() => {}};
      (window as Window & {__delayedDraft?:typeof state}).__delayedDraft = state;
      state.release = () => state.pending.splice(0).forEach(complete => complete());
      const reads = new WeakSet<IDBTransaction>();
      const get = IDBObjectStore.prototype.get;
      IDBObjectStore.prototype.get = function (query) {
        if (this.name === 'drafts' && query === key) reads.add(this.transaction);
        return get.call(this, query);
      };
      const descriptor = Object.getOwnPropertyDescriptor(IDBTransaction.prototype, 'oncomplete')!;
      Object.defineProperty(IDBTransaction.prototype, 'oncomplete', {
        ...descriptor,
        set(handler:((event:Event) => void) | null) {
          descriptor.set!.call(this, handler ? function (this:IDBTransaction, event:Event) {
            if (reads.has(this)) state.pending.push(() => handler.call(this, event));
            else handler.call(this, event);
          } : null);
        },
      });
    }, scenario.draftKey);
    await page.reload();
    await page.waitForFunction(() => Boolean((window as Window & {__delayedDraft?:{pending:unknown[]}}).__delayedDraft?.pending.length));
    await scenario.edit(page).fill(newValue);
    await expect(scenario.run(page)).toBeEnabled();
    await scenario.run(page).click();
    await expect(scenario.approved(page)).toBeEnabled();
    await page.evaluate(() => (window as Window & {__delayedDraft?:{release:() => void}}).__delayedDraft?.release());
    await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
    await expect(scenario.edit(page)).toHaveValue(newValue);
    await expect(scenario.approved(page)).toBeEnabled();
  });
}

test('empty architecture undo and redo do not abandon a running verification', async ({page}) => {
  await ready(page);
  let release!: () => void;
  let started!: () => void;
  const held = new Promise<void>(resolve => { release = resolve; });
  const intercepted = new Promise<void>(resolve => { started = resolve; });
  await page.route('**/api/v1/architecture/designs/run', async route => {
    started(); await held; await route.fulfill({json:passed});
  });
  await page.goto('/');
  await expect(page.getByTestId('architecture-undo')).toBeDisabled();
  await expect(page.getByTestId('architecture-redo')).toBeDisabled();
  const run = page.getByTestId('architecture-run-verification');
  await expect(run).toBeEnabled();
  await run.click();
  await intercepted;
  await page.keyboard.press('Control+z');
  await page.keyboard.press('Control+Shift+z');
  release();
  await expect(page.getByTestId('architecture-demo')).toHaveAttribute('data-verification-status', 'passed');
  await expect(page.getByTestId('architecture-download')).toBeEnabled();
  await expect(run).toBeEnabled();
});

test('piping valve drag uses SVG scale when the canvas is letterboxed', async ({page}) => {
  await ready(page);
  await page.goto('/piping');
  await page.addStyleTag({content:'svg.piping-canvas { width:100%; height:240px !important; min-height:240px !important; aspect-ratio:auto !important; }'});
  const valve = page.getByTestId('piping-draggable-valve');
  await valve.scrollIntoViewIfNeeded();
  const offset = Number(await page.locator('#piping-valve-offset').inputValue());
  const bounds = (await valve.boundingBox())!;
  const scales = await page.getByTestId('piping-canvas').evaluate((node: SVGSVGElement) => ({
    actual:node.getScreenCTM()!.a, naive:node.getBoundingClientRect().width/node.viewBox.baseVal.width,
  }));
  expect(Math.abs(scales.actual - scales.naive)).toBeGreaterThan(0.005);
  const x = bounds.x + bounds.width / 2;
  const y = bounds.y + bounds.height / 2;
  await page.mouse.move(x,y);
  await page.mouse.down();
  await page.mouse.move(x + 500 * scales.actual,y,{steps:5});
  await page.mouse.up();
  await expect(page.locator('#piping-valve-offset')).toHaveValue(String(offset + 500));
});
