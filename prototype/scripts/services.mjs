import { createConnection } from 'node:net';

async function portIsOpen(port, timeoutMs) {
  return new Promise((resolve, reject) => {
    const socket = createConnection({ host: '127.0.0.1', port });
    const finish = (error, open) => {
      socket.destroy();
      if (error) reject(error);
      else resolve(open);
    };
    socket.setTimeout(timeoutMs);
    socket.once('connect', () => finish(null, true));
    socket.once('error', error => error.code === 'ECONNREFUSED' ? finish(null, false) : finish(error));
    socket.once('timeout', () => finish(new Error(`Timed out checking local port ${port}.`)));
  });
}

export async function matchesStriveTrack(url, kind, timeoutMs = 1500) {
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(timeoutMs), redirect: 'error' });
    if (!response.ok) return false;
    if (kind === 'backend') {
      const body = await response.json();
      return body.status === 'ok' && body.mode === 'local-demo';
    }
    return /<title>\s*StriveTrack(?:\s|—|-|<)/i.test(await response.text());
  } catch {
    return false;
  }
}

export async function inspectService({ port, kind }, timeoutMs = 1500) {
  if (!await portIsOpen(port, timeoutMs)) return 'free';
  const route = kind === 'backend' ? '/api/health' : '/';
  return await matchesStriveTrack(`http://127.0.0.1:${port}${route}`, kind, timeoutMs) ? 'strivetrack' : 'occupied';
}
