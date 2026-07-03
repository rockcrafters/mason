// black-box tests for the installer: run the real cli.js against throwaway temp
// targets and assert on stdout + the resulting filesystem. no deps, node builtin
// runner: `node --test tests/scripts/`.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

const CLI = path.resolve(__dirname, '..', '..', 'scripts', 'cli.js');

function tmpTarget() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'mason-test-'));
  fs.mkdirSync(path.join(dir, '.claude')); // claude marker so auto-detect has something
  return dir;
}

// run the installer, return stdout. never throws for the flows we test (install
// exits 0 even with conflict warnings, which go to stderr).
function run(target, extra = []) {
  return execFileSync('node', [CLI, 'install', '--target', target, ...extra], { encoding: 'utf-8' });
}

const claudeSkill = (target, skill) => path.join(target, '.claude', 'skills', skill, 'SKILL.md');

test('dry-run writes nothing', () => {
  const t = tmpTarget();
  const out = run(t, ['--agents', 'claude', '--dry-run']);
  assert.match(out, /would write:/);
  assert.ok(!fs.existsSync(claudeSkill(t, 'mason')), 'dry-run must not create files');
});

test('fresh install lands both skills', () => {
  const t = tmpTarget();
  run(t, ['--agents', 'claude']);
  assert.ok(fs.existsSync(claudeSkill(t, 'mason')));
  assert.ok(fs.existsSync(claudeSkill(t, 'chisel')));
});

test('shared/ is materialised into every skill from mason/_shared', () => {
  const t = tmpTarget();
  run(t, ['--agents', 'claude']);
  const src = path.resolve(__dirname, '..', '..', 'mason', '_shared', 'CHISEL.md');
  for (const skill of ['chisel', 'mason']) {
    const dst = path.join(t, '.claude', 'skills', skill, 'shared', 'CHISEL.md');
    assert.ok(fs.existsSync(dst), `${skill} must get shared/CHISEL.md`);
    assert.deepEqual(fs.readFileSync(dst), fs.readFileSync(src), 'materialised copy must match source');
  }
});

test('re-install of identical files is up-to-date, no rewrite', () => {
  const t = tmpTarget();
  run(t, ['--agents', 'claude']);
  const before = fs.statSync(claudeSkill(t, 'mason')).mtimeMs;
  const out = run(t, ['--agents', 'claude']);
  assert.match(out, /up-to-date:/);
  assert.equal(fs.statSync(claudeSkill(t, 'mason')).mtimeMs, before, 'unchanged file must not be rewritten');
});

test('differing file without force is a conflict, left untouched', () => {
  const t = tmpTarget();
  run(t, ['--agents', 'claude']);
  fs.writeFileSync(claudeSkill(t, 'mason'), 'local edit');
  // conflict warning goes to stderr; capture it.
  const res = execFileSync('node', [CLI, 'install', '--target', t, '--agents', 'claude'],
    { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'pipe'] });
  assert.equal(fs.readFileSync(claudeSkill(t, 'mason'), 'utf-8'), 'local edit', 'conflict must not clobber');
  assert.match(res, /up-to-date:|wrote:/); // other files still process
});

test('force overwrites a differing file', () => {
  const t = tmpTarget();
  run(t, ['--agents', 'claude']);
  fs.writeFileSync(claudeSkill(t, 'mason'), 'local edit');
  run(t, ['--agents', 'claude', '--force']);
  assert.notEqual(fs.readFileSync(claudeSkill(t, 'mason'), 'utf-8'), 'local edit', 'force must overwrite');
});

test('force drops a stale file in the skill dir but keeps foreign sibling skills', () => {
  const t = tmpTarget();
  run(t, ['--agents', 'claude']);
  const stale = path.join(t, '.claude', 'skills', 'mason', 'STALE.md');
  fs.writeFileSync(stale, 'stale');
  const sibling = path.join(t, '.claude', 'skills', 'other-skill', 'SKILL.md');
  fs.mkdirSync(path.dirname(sibling));
  fs.writeFileSync(sibling, 'keep');

  run(t, ['--agents', 'claude', '--force']);

  assert.ok(!fs.existsSync(stale), 'stale file inside a known skill must be dropped');
  assert.ok(fs.existsSync(claudeSkill(t, 'mason')), 'skill must be rewritten after wipe');
  assert.equal(fs.readFileSync(sibling, 'utf-8'), 'keep', 'foreign sibling skill must survive');
});

test('dry-run + force reports would-drop but deletes nothing', () => {
  const t = tmpTarget();
  run(t, ['--agents', 'claude']);
  const stale = path.join(t, '.claude', 'skills', 'mason', 'STALE.md');
  fs.writeFileSync(stale, 'stale');
  const out = run(t, ['--agents', 'claude', '--force', '--dry-run']);
  assert.match(out, /would drop:/);
  assert.ok(fs.existsSync(stale), 'dry-run must not delete');
});

test('auto-detect finds claude via its marker dir', () => {
  const t = tmpTarget(); // tmpTarget already creates .claude
  const out = run(t); // no --agents
  assert.match(out, /agents: claude \[auto-detect\]/);
});

test('unknown agent name is filtered out', () => {
  const t = tmpTarget();
  const out = run(t, ['--agents', 'claude,bogus']);
  assert.match(out, /agents: claude /);
  assert.doesNotMatch(out, /bogus/);
});

test('opencode gets a command dispatcher per skill', () => {
  const t = tmpTarget();
  run(t, ['--agents', 'opencode']);
  assert.ok(fs.existsSync(path.join(t, '.opencode', 'command', 'mason.md')));
  assert.ok(fs.existsSync(path.join(t, '.opencode', 'command', 'chisel.md')));
});
