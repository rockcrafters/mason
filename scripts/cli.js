#!/usr/bin/env node
// mason cross-agent skill installer. zero-dep.
//   npx github:rockcrafters/mason install [--agents claude,pi,copilot,opencode]
//                                         [--target <dir>] [--dry-run] [--force]
// copies each self-contained skill tree (mason/skills/<skill>/) into each agent's
// skill-discovery dir. opencode also gets real command .md files for its loader.
// NOTE: no install-state tracking -- re-install skips files that differ from
// source (warns to use --force) and never silently clobbers local edits.
// --force is a clean per-skill reinstall: it drops <base>/<skill> then rewrites,
// so stale files vanish. scoped to the skill dir, never the whole skills base.

const fs = require('node:fs');
const path = require('node:path');
const { parseArgs } = require('node:util');
const { execSync } = require('node:child_process');

const PKG_ROOT = path.resolve(__dirname, '..');
const SKILLS_ROOT = path.join(PKG_ROOT, 'mason', 'skills'); // one dir per skill (chisel, ...)
const SUPPORTED = ['claude', 'pi', 'copilot', 'opencode', 'codex'];

// base dir each agent scans for skills, relative to target. each skill installs to <base>/<skill>.
const SKILL_BASE = {
  claude: '.claude/skills',
  pi: '.pi/skills',
  copilot: '.github/skills',
  opencode: '.opencode/skills',
  codex: '.codex/skills',
};

// marker paths whose presence in target implies the agent is in use.
const MARKERS = {
  claude: ['.claude', 'CLAUDE.md'],
  pi: ['.pi'],
  copilot: ['.github/copilot-instructions.md', '.github/prompts'],
  opencode: ['opencode.json', '.opencode'],
  codex: ['.codex'],
};

const HELP = `mason -- cross-agent chisel slice skill installer

usage:
  npx github:rockcrafters/mason install [options]

options:
  --agents <list>   comma-separated: ${SUPPORTED.join(', ')} (default: auto-detect)
  --target <dir>    install into <dir> (default: git root, else cwd)
  --dry-run         show what would change, write nothing
  --force           clean reinstall: drop each skill dir, then write it anew
  --quiet, -q       suppress per-file logs (warnings still print)
  --help, -h        show this help

examples:
  npx github:rockcrafters/mason install --agents claude
  npx github:rockcrafters/mason install --dry-run
`;

function gitRoot(dir) {
  try {
    return execSync('git rev-parse --show-toplevel', { cwd: dir, encoding: 'utf-8', stdio: ['ignore', 'pipe', 'ignore'] }).trim() || null;
  } catch { return null; }
}

function resolveTarget(arg) {
  if (arg) return path.resolve(arg);
  const start = path.resolve(process.env.INIT_CWD || process.cwd());
  return gitRoot(start) || start;
}

function detectAgents(target) {
  return SUPPORTED.filter((a) => MARKERS[a].some((m) => fs.existsSync(path.join(target, m))));
}

function listFiles(root) {
  const out = [];
  for (const e of fs.readdirSync(root, { withFileTypes: true })) {
    const p = path.join(root, e.name);
    if (e.isDirectory()) out.push(...listFiles(p));
    else if (e.isFile()) out.push(p);
  }
  return out;
}

// returns 'write' | 'skip' | 'conflict'
function plan(srcContent, dst, force) {
  if (!fs.existsSync(dst)) return 'write';
  const cur = fs.readFileSync(dst);
  if (cur.equals(srcContent)) return 'skip';
  return force ? 'write' : 'conflict';
}

function placeFile(srcContent, dst, opts, logs, warns, mode) {
  const rel = path.relative(opts.target, dst);
  const action = plan(srcContent, dst, opts.force);
  if (action === 'skip') { logs.push(`up-to-date: ${rel}`); return; }
  if (action === 'conflict') { warns.push(`differs (use --force): ${rel}`); return; }
  if (opts.dryRun) { logs.push(`would write: ${rel}`); return; }
  fs.mkdirSync(path.dirname(dst), { recursive: true });
  fs.writeFileSync(dst, srcContent);
  if (mode !== undefined) fs.chmodSync(dst, mode); // preserve +x so scripts/ run when invoked by path
  logs.push(`wrote: ${rel}`);
}

// --force does a clean reinstall of one skill: drop <base>/<skill> then write anew,
// so files removed from source don't linger. scoped to the skill dir -- sibling
// skills (and anything else under the skills base) are left untouched.
function wipeSkill(dir, opts, logs) {
  if (!fs.existsSync(dir)) return;
  const rel = path.relative(opts.target, dir);
  if (opts.dryRun) { logs.push(`would drop: ${rel}/`); return; }
  fs.rmSync(dir, { recursive: true, force: true });
  logs.push(`dropped: ${rel}/`);
}

function copyTree(srcRoot, dstRoot, opts, logs, warns) {
  for (const src of listFiles(srcRoot)) {
    const dst = path.join(dstRoot, path.relative(srcRoot, src));
    placeFile(fs.readFileSync(src), dst, opts, logs, warns, fs.statSync(src).mode);
  }
}

function listSkills() {
  return fs.readdirSync(SKILLS_ROOT, { withFileTypes: true })
    .filter((e) => e.isDirectory() && fs.existsSync(path.join(SKILLS_ROOT, e.name, 'SKILL.md')))
    .map((e) => e.name);
}

function install(opts) {
  const logs = [];
  const warns = [];
  if (!fs.existsSync(SKILLS_ROOT)) throw new Error(`missing skills payload: ${SKILLS_ROOT}`);
  const skills = listSkills();

  let agents = opts.agents;
  let source = '--agents';
  if (!agents.length) {
    const env = (process.env.MASON_AGENTS || '').split(',').map((s) => s.trim().toLowerCase()).filter((a) => SUPPORTED.includes(a));
    if (env.length) { agents = env; source = 'MASON_AGENTS'; }
    else { agents = detectAgents(opts.target); source = 'auto-detect'; }
  }
  agents = [...new Set(agents)];

  logs.push(`target: ${opts.target}`);
  logs.push(`skills: ${skills.join(', ')}`);
  logs.push(`agents: ${agents.join(', ') || '(none)'} [${source}]`);
  logs.push(`mode: ${opts.dryRun ? 'dry-run' : 'write'}${opts.force ? ', force' : ''}`);

  if (!agents.length) {
    warns.push('no agents selected or detected. pass --agents to choose.');
    return { logs, warns };
  }

  for (const agent of agents) {
    logs.push(`-- ${agent} --`);
    for (const skill of skills) {
      const src = path.join(SKILLS_ROOT, skill);
      const dstRoot = path.join(opts.target, SKILL_BASE[agent], skill);
      if (opts.force) wipeSkill(dstRoot, opts, logs);
      copyTree(src, dstRoot, opts, logs, warns);
      if (agent === 'opencode') {
        // single dispatcher so `/<skill> <subcmd>` works like in claude
        const dispatcher = Buffer.from(
          `---
description: ${skill} skill
---

Use the ${skill} skill. Sub-command: $ARGUMENTS
`);
        placeFile(dispatcher, path.join(opts.target, '.opencode/command', `${skill}.md`), opts, logs, warns);
      }
      // pi loads the skill natively from .pi/skills/<skill>/ -- no extra prompt command needed.
    }
  }
  return { logs, warns };
}

function main() {
  const argv = process.argv.slice(2);

  // help wins over everything, even alongside malformed args.
  if (argv.includes('-h') || argv.includes('--help')) {
    process.stdout.write(HELP);
    process.exit(0);
  }

  let values;
  let positionals;
  try {
    ({ values, positionals } = parseArgs({
      allowPositionals: true,
      options: {
        agents: { type: 'string' },
        target: { type: 'string' },
        'dry-run': { type: 'boolean' },
        force: { type: 'boolean' },
        quiet: { type: 'boolean', short: 'q' },
        help: { type: 'boolean', short: 'h' },
      },
    }));
  } catch (e) {
    process.stderr.write(`${e.message}\n\n`);
    process.stderr.write(HELP);
    process.exit(1);
  }

  if (positionals[0] !== 'install') {
    process.stdout.write(HELP);
    process.exit(positionals.length ? 1 : 0);
  }

  const opts = {
    target: resolveTarget(values.target),
    agents: (values.agents || '').split(',').map((s) => s.trim().toLowerCase()).filter(Boolean).filter((a) => SUPPORTED.includes(a)),
    dryRun: Boolean(values['dry-run']),
    force: Boolean(values.force),
    quiet: Boolean(values.quiet),
  };

  try {
    const { logs, warns } = install(opts);
    if (!opts.quiet) for (const l of logs) process.stdout.write(`${l}\n`);
    for (const w of warns) process.stderr.write(`warning: ${w}\n`);
  } catch (e) {
    process.stderr.write(`install failed: ${e.message}\n`);
    process.exit(1);
  }
}

main();
