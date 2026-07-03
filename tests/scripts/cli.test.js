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
  const out = run(t, ['claude', '--dry-run']);
  assert.match(out, /would write:/);
  assert.ok(!fs.existsSync(claudeSkill(t, 'mason')), 'dry-run must not create files');
});

test('fresh install lands both skills', () => {
  const t = tmpTarget();
  run(t, ['claude']);
  assert.ok(fs.existsSync(claudeSkill(t, 'mason')));
  assert.ok(fs.existsSync(claudeSkill(t, 'chisel-releases')));
});

test('shared/ is materialised into every skill from mason/_shared', () => {
  const t = tmpTarget();
  run(t, ['claude']);
  const src = path.resolve(__dirname, '..', '..', 'mason', '_shared', 'CHISEL.md');
  for (const skill of ['chisel-releases', 'mason']) {
    const dst = path.join(t, '.claude', 'skills', skill, 'shared', 'CHISEL.md');
    assert.ok(fs.existsSync(dst), `${skill} must get shared/CHISEL.md`);
    assert.deepEqual(fs.readFileSync(dst), fs.readFileSync(src), 'materialised copy must match source');
  }
});

test('re-install of identical files is up-to-date, no rewrite', () => {
  const t = tmpTarget();
  run(t, ['claude']);
  const before = fs.statSync(claudeSkill(t, 'mason')).mtimeMs;
  const out = run(t, ['claude']);
  assert.match(out, /up-to-date:/);
  assert.equal(fs.statSync(claudeSkill(t, 'mason')).mtimeMs, before, 'unchanged file must not be rewritten');
});

test('differing file without force is a conflict, left untouched', () => {
  const t = tmpTarget();
  run(t, ['claude']);
  fs.writeFileSync(claudeSkill(t, 'mason'), 'local edit');
  // conflict warning goes to stderr; capture it.
  const res = execFileSync('node', [CLI, 'install', '--target', t, 'claude'],
    { encoding: 'utf-8', stdio: ['ignore', 'pipe', 'pipe'] });
  assert.equal(fs.readFileSync(claudeSkill(t, 'mason'), 'utf-8'), 'local edit', 'conflict must not clobber');
  assert.match(res, /up-to-date:|wrote:/); // other files still process
});

test('force overwrites a differing file', () => {
  const t = tmpTarget();
  run(t, ['claude']);
  fs.writeFileSync(claudeSkill(t, 'mason'), 'local edit');
  run(t, ['claude', '--force']);
  assert.notEqual(fs.readFileSync(claudeSkill(t, 'mason'), 'utf-8'), 'local edit', 'force must overwrite');
});

test('force drops a stale file in the skill dir but keeps foreign sibling skills', () => {
  const t = tmpTarget();
  run(t, ['claude']);
  const stale = path.join(t, '.claude', 'skills', 'mason', 'STALE.md');
  fs.writeFileSync(stale, 'stale');
  const sibling = path.join(t, '.claude', 'skills', 'other-skill', 'SKILL.md');
  fs.mkdirSync(path.dirname(sibling));
  fs.writeFileSync(sibling, 'keep');

  run(t, ['claude', '--force']);

  assert.ok(!fs.existsSync(stale), 'stale file inside a known skill must be dropped');
  assert.ok(fs.existsSync(claudeSkill(t, 'mason')), 'skill must be rewritten after wipe');
  assert.equal(fs.readFileSync(sibling, 'utf-8'), 'keep', 'foreign sibling skill must survive');
});

test('dry-run + force reports would-drop but deletes nothing', () => {
  const t = tmpTarget();
  run(t, ['claude']);
  const stale = path.join(t, '.claude', 'skills', 'mason', 'STALE.md');
  fs.writeFileSync(stale, 'stale');
  const out = run(t, ['claude', '--force', '--dry-run']);
  assert.match(out, /would drop:/);
  assert.ok(fs.existsSync(stale), 'dry-run must not delete');
});

test('bare invocation without subcommand exits nonzero with help', () => {
  assert.throws(() => execFileSync('node', [CLI], { encoding: 'utf-8' }), /usage:/);
});

test('missing agents arg is an error, installs nothing', () => {
  const t = tmpTarget();
  assert.throws(() => run(t), /missing required agents list/);
  assert.ok(!fs.existsSync(path.join(t, '.claude', 'skills')), 'must not install without agents arg');
});

test('agents=auto detects claude via its marker dir', () => {
  const t = tmpTarget(); // tmpTarget already creates .claude
  const out = run(t, ['auto']);
  assert.match(out, /agents: claude\n/);
  assert.ok(fs.existsSync(claudeSkill(t, 'mason')));
});

test('agents=auto with no markers says so and installs nothing', () => {
  const t = fs.mkdtempSync(path.join(os.tmpdir(), 'mason-test-')); // no marker dirs
  const out = run(t, ['auto']);
  assert.match(out, /no agent markers found in target; nothing to install\./);
  assert.ok(!fs.existsSync(path.join(t, '.claude')), 'must not install anything');
});

test('duplicate agents collapse to one install', () => {
  const t = tmpTarget();
  const out = run(t, ['claude,claude,claude']);
  assert.equal(out.match(/-- claude --/g).length, 1, 'claude must be installed once');
});

test('explicit agents mix with auto', () => {
  const t = tmpTarget(); // has .claude marker -> auto finds claude
  const out = run(t, ['codex,auto']);
  assert.match(out, /agents: codex, claude\n/);
  assert.ok(fs.existsSync(path.join(t, '.codex', 'skills', 'mason', 'SKILL.md')));
  assert.ok(fs.existsSync(claudeSkill(t, 'mason')));
});

test('agents=all installs every agent, short-circuits auto', () => {
  const t = fs.mkdtempSync(path.join(os.tmpdir(), 'mason-test-')); // no markers: auto would find nothing
  const out = run(t, ['claude,auto,codex,all']);
  assert.match(out, /agents: claude, pi, copilot, opencode, codex\n/);
  for (const base of ['.claude/skills', '.pi/skills', '.github/skills', '.opencode/skills', '.codex/skills']) {
    assert.ok(fs.existsSync(path.join(t, base, 'mason', 'SKILL.md')), `${base} must be installed`);
  }
});

test('agents=auto respects dry-run: detection works, nothing written', () => {
  const t = tmpTarget();
  const out = run(t, ['auto', '--dry-run']);
  assert.match(out, /agents: claude\n/);
  assert.match(out, /would write:/);
  assert.ok(!fs.existsSync(claudeSkill(t, 'mason')), 'dry-run must not create files');
});

test('unknown agent name is filtered out', () => {
  const t = tmpTarget();
  const out = run(t, ['claude,bogus']);
  assert.match(out, /agents: claude\n/);
  assert.doesNotMatch(out, /bogus/);
});

test('only unknown agent names is an error', () => {
  const t = tmpTarget();
  assert.throws(() => run(t, ['bogus']), /no valid agents given/);
});

test('--update behaves as --force', () => {
  const t = tmpTarget();
  run(t, ['claude']);
  fs.writeFileSync(claudeSkill(t, 'mason'), 'local edit');
  run(t, ['claude', '--update']);
  assert.notEqual(fs.readFileSync(claudeSkill(t, 'mason'), 'utf-8'), 'local edit', 'update must overwrite like force');
});

test('opencode gets a command dispatcher per skill', () => {
  const t = tmpTarget();
  run(t, ['opencode']);
  assert.ok(fs.existsSync(path.join(t, '.opencode', 'command', 'mason.md')));
  assert.ok(fs.existsSync(path.join(t, '.opencode', 'command', 'chisel-releases.md')));
});
