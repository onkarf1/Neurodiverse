import { chromium } from '../frontend/node_modules/playwright/index.mjs';
import { mkdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
const artifacts = fileURLToPath(new URL('../.cache/preview/', import.meta.url));
mkdirSync(`${artifacts}tmp`, { recursive: true });
process.env.TMPDIR = `${artifacts}tmp`;
const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH, headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 }, reducedMotion: 'reduce' });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('http://127.0.0.1:5173/login');
  await page.getByRole('button', { name: /Maya Brooks/ }).waitFor();
  await page.screenshot({ path: `${artifacts}login.png`, fullPage: true });
  await page.getByRole('button', { name: /Maya Brooks/ }).click();
  await page.getByRole('button', { name: 'Step into your workspace' }).click();
  await page.getByRole('heading', { name: 'Good to see you, Maya.' }).waitFor();
  await page.waitForTimeout(350);
  await page.screenshot({ path: `${artifacts}dashboard.png`, fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(350);
  console.log('Mobile overflow:', JSON.stringify(await page.evaluate(() => {
    const width = document.documentElement.clientWidth;
    return { viewport: width, scrollWidth: document.documentElement.scrollWidth, elements: [...document.querySelectorAll('body *')].filter(el => { const r = el.getBoundingClientRect(); return r.width && (r.right > width + 1 || r.left < -1) }).map(el => ({ tag: el.tagName, class: el.className, width: el.getBoundingClientRect().width, right: el.getBoundingClientRect().right })).slice(0, 80) };
  })));
  await page.screenshot({ path: `${artifacts}mobile.png`, fullPage: true });
  await page.goto('http://127.0.0.1:5173/check?activity=a01');
  await page.getByRole('heading', { name: 'Alignment check', exact: true }).waitFor();
  await page.screenshot({ path: `${artifacts}check-mobile.png`, fullPage: true });
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    for (const route of ['/', '/goals', '/activities', '/check?activity=a01', '/try/a02', '/history']) {
      await page.goto(`http://127.0.0.1:5173${route}`, { waitUntil: 'networkidle' });
      const fits = await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1);
      console.log(`Layout ${width}px ${route}: ${fits ? 'PASS' : 'OVERFLOW'}`);
      if (!fits) throw new Error(`Horizontal page overflow at ${width}px ${route}`);
    }
  }
  console.log('Browser errors:', JSON.stringify(errors));
  console.log(`Preview images saved to ${artifacts}`);
} finally { await browser.close() }
