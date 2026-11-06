import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { createServer as createTcpServer } from 'node:net';
import { inspectService, matchesStriveTrack } from './services.mjs';

async function listen(server, t) {
  const sockets = new Set();
  server.on('connection', socket => { sockets.add(socket); socket.on('close', () => sockets.delete(socket)); });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  t.after(() => new Promise(resolve => { server.close(resolve); sockets.forEach(socket => socket.destroy()); }));
  return server.address().port;
}

test('an existing StriveTrack backend is reusable without starting another server', async t => {
  const port = await listen(createServer((req, res) => {
    assert.equal(req.url, '/api/health');
    res.setHeader('content-type', 'application/json');
    res.end(JSON.stringify({ status: 'ok', mode: 'local-demo' }));
  }), t);
  assert.equal(await inspectService({ port, kind: 'backend' }), 'strivetrack');
});

test('an existing frontend is recognized and its API proxy is checked separately', async t => {
  const port = await listen(createServer((req, res) => {
    if (req.url === '/') res.end('<html><title>StriveTrack — Small steps, meaningful progress</title></html>');
    else { res.statusCode = 502; res.end('Backend unavailable'); }
  }), t);
  assert.equal(await inspectService({ port, kind: 'frontend' }), 'strivetrack');
  assert.equal(await matchesStriveTrack(`http://127.0.0.1:${port}/api/health`, 'backend'), false);
});

test('an unrelated HTTP service is occupied rather than reusable', async t => {
  const port = await listen(createServer((_req, res) => res.end('<title>Another project</title>')), t);
  assert.equal(await inspectService({ port, kind: 'frontend' }), 'occupied');
  assert.equal(await inspectService({ port, kind: 'backend' }), 'occupied');
});

test('a silent non-HTTP listener cannot hang the launcher', async t => {
  const port = await listen(createTcpServer(), t);
  assert.equal(await inspectService({ port, kind: 'backend' }, 100), 'occupied');
});

test('a free port can be used to start a missing service', async () => {
  const server = createTcpServer();
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  assert.equal(await inspectService({ port, kind: 'backend' }), 'free');
});
