import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const root = fileURLToPath(new URL('../', import.meta.url));
const python = path.join(root, 'backend', '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
const result = spawnSync(python, ['-m', 'pytest', '-q'], { cwd: path.join(root, 'backend'), stdio: 'inherit', env: { ...process.env, PYTHONPYCACHEPREFIX: path.join(root, '.cache', 'pycache') } });
if (result.error) console.error('Run npm run setup first.', result.error.message);
process.exit(result.status ?? 1);
