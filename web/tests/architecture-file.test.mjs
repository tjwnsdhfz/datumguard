import test from 'node:test';
import assert from 'node:assert/strict';
import { parseArchitecture, serializeArchitecture } from '../lib/architecture-file.ts';
const draft = () => ({ presetId:'architecture-studio', projectName:'내 도면', revision:'B', snap:50, grids:[], walls:[{id:'w',start:[0,0],end:[1000,0],thickness:200,wall_type:'exterior'}], openings:[], columns:[], roomSeeds:[] });
test('round trips editable input without importing a verification result', () => {
  assert.deepEqual(parseArchitecture(serializeArchitecture(draft())),draft());
});
test('rejects unknown version, malformed file, and excessive input', () => {
  assert.throws(()=>parseArchitecture('{}'));
  assert.throws(()=>parseArchitecture('{'));
  assert.throws(()=>parseArchitecture(' '.repeat(1048577)));
  assert.throws(()=>parseArchitecture(JSON.stringify({format:'datumguard-architecture',version:2,draft:draft()})));
});
test('rejects broken object references, duplicate IDs and invalid geometry values', () => {
  const a=draft(); a.openings=[{id:'o',type:'door',wall_id:'missing',offset:0,width:800}];
  assert.throws(()=>parseArchitecture(serializeArchitecture(a)),/연결된 벽/);
  const b=draft(); b.walls.push({...b.walls[0]}); assert.throws(()=>parseArchitecture(serializeArchitecture(b)),/중복/);
  const c=draft(); c.walls[0].thickness=-1; assert.throws(()=>parseArchitecture(serializeArchitecture(c)),/두께/);
  const d=draft(); d.walls[0].start=[null,0]; assert.throws(()=>parseArchitecture(serializeArchitecture(d)));
});
