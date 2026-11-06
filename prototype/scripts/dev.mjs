import { spawn } from 'node:child_process';
import { existsSync, mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { inspectService, matchesStriveTrack } from './services.mjs';

const root = fileURLToPath(new URL('../', import.meta.url));
const python = path.join(root, 'backend', '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
if (!existsSync(python) || !existsSync(path.join(root, 'frontend', 'node_modules'))) { console.error('Run npm run setup first.'); process.exit(1) }
mkdirSync(path.join(root, '.cache'), { recursive: true });
const env = { ...process.env, PYTHONPYCACHEPREFIX: path.join(root, '.cache', 'pycache'), npm_config_cache: path.join(root, '.cache', 'npm') };
const children = [];
let stopping = false;
function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  const running = children.filter(child => child.exitCode === null && child.signalCode === null);
  if (!running.length) process.exit(code);
  let remaining = running.length;
  const deadline = setTimeout(() => {
    running.forEach(child => { if (child.exitCode === null && child.signalCode === null) child.kill('SIGKILL'); });
    process.exit(code);
  }, 3000);
  running.forEach(child => {
    child.once('close', () => { if (--remaining === 0) { clearTimeout(deadline); process.exit(code); } });
    child.kill('SIGTERM');
  });
}
function start(command, args, cwd) {
  const child = spawn(command, args, { cwd, env, stdio: 'inherit', shell: process.platform === 'win32' && command.endsWith('.cmd') });
  children.push(child);
  child.on('error', error => { console.error(error.message); stop(1) });
  child.on('exit', code => { if (!stopping) { console.error('A StriveTrack server stopped unexpectedly.'); stop(code || 1); } });
}
process.on('SIGINT', () => stop());
process.on('SIGTERM', () => stop());

try {
  // Inspect both ports before starting either process. Existing services are never stopped.
  const [backend, frontend] = await Promise.all([
    inspectService({ port: 8001, kind: 'backend' }),
    inspectService({ port: 5173, kind: 'frontend' }),
  ]);
  for (const [port, state] of [[8001, backend], [5173, frontend]]) {
    if (state === 'occupied') throw new Error(`Port ${port} is occupied by a service that did not identify as StriveTrack. Stop that service in its own terminal, then rerun npm run dev.`);
  }
  if (backend === 'strivetrack') console.log('Using the existing StriveTrack backend on port 8001.');
  else start(python, ['-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8001'], path.join(root, 'backend'));
  if (frontend === 'strivetrack') console.log('Using the existing StriveTrack frontend on port 5173.');
  else start(process.execPath, [path.join(root, 'frontend', 'node_modules', 'vite', 'bin', 'vite.js'), '--host', '127.0.0.1'], path.join(root, 'frontend'));

  let ready = false;
  const deadline = Date.now() + 10_000;
  do {
    const results = await Promise.all([
      matchesStriveTrack('http://127.0.0.1:8001/api/health', 'backend'),
      matchesStriveTrack('http://127.0.0.1:5173/api/health', 'backend'),
    ]);
    ready = results.every(Boolean);
    if (ready) break;
    if (backend === 'strivetrack' && frontend === 'strivetrack') break;
    await new Promise(resolve => setTimeout(resolve, 250));
  } while (Date.now() < deadline && !stopping);
  if (!ready) throw new Error('The frontend could not reach the StriveTrack backend. Check that its /api proxy uses http://127.0.0.1:8001, then restart the affected server.');
  console.log(backend === 'strivetrack' && frontend === 'strivetrack' ? '\nStriveTrack is already running. Open http://127.0.0.1:5173' : '\nStriveTrack is ready. Open http://127.0.0.1:5173');
  console.log('API docs: http://127.0.0.1:8001/docs');
  if (!children.length) process.exit(0);
  console.log('Ctrl+C stops the servers started by this command. Reused servers stay in their original terminal.');
} catch (error) {
  console.error(error.message);
  stop(1);
}
