import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('../', import.meta.url));
const cache = path.join(root, '.cache');
mkdirSync(cache, { recursive: true });
const env = { ...process.env, PIP_CACHE_DIR: path.join(cache, 'pip'), PYTHONPYCACHEPREFIX: path.join(cache, 'pycache'), npm_config_cache: path.join(cache, 'npm') };
const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm';
function run(command, args, cwd = root) {
  const result = spawnSync(command, args, { cwd, env, stdio: 'inherit', shell: process.platform === 'win32' && command === npm });
  if (result.error || result.status !== 0) { console.error(result.error?.message || `Command failed: ${command}`); process.exit(result.status || 1) }
}
let python = process.env.STRIVETRACK_PYTHON;
if (!python) {
  python = ['python3.12', 'python3.11', 'python3.10', 'python3', 'python'].find(candidate => {
    const probe = spawnSync(candidate, ['-c', 'import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)'], { env, stdio: 'ignore' });
    return probe.status === 0;
  });
}
if (!python) { console.error('Install Python 3.9 or newer, then rerun npm run setup.'); process.exit(1) }
const venvPython = path.join(root, 'backend', '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
if (!existsSync(venvPython)) run(python, ['-m', 'venv', path.join(root, 'backend', '.venv')]);
run(venvPython, ['-m', 'pip', 'install', '-r', path.join(root, 'requirements.txt'), '--disable-pip-version-check']);
run(npm, ['install', '--no-audit', '--no-fund'], path.join(root, 'frontend'));
console.log('\nStriveTrack is ready. Run npm run dev, then open http://127.0.0.1:5173');
