import { expect, test, type Page } from '@playwright/test';

const backend = 'http://127.0.0.1:8001/api';
let demoToken = '';

async function openAsTeacher(page: Page, path = '/') {
  await page.addInitScript(token => localStorage.setItem('strivetrack-token', token), demoToken);
  await page.goto(path);
}

async function confirmOpenDialog(page: Page) {
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('button', { name: 'Confirm', exact: true }).click();
  await expect(dialog).toBeHidden();
}

// Reset through the real API before each test; no database or source-file shortcuts.
test.beforeEach(async ({ request }) => {
  const login = await request.post(`${backend}/auth/login`, {
    data: { email: 'teacher@strivetrack.demo', password: 'strivetrack-demo' },
  });
  expect(login.ok(), 'Start the FastAPI backend before running browser tests.').toBeTruthy();
  demoToken = (await login.json()).token;
  const reset = await request.post(`${backend}/reset`, { headers: { Authorization: `Bearer ${demoToken}` } });
  expect(reset.ok()).toBeTruthy();
});

test('demo sign-in opens the seeded overview, stats, and weekly chart', async ({ page }) => {
  await page.goto('/login');
  await page.getByRole('button', { name: /Maya Brooks/ }).click();
  await expect(page.getByLabel('Email address')).toHaveValue('teacher@strivetrack.demo');
  await page.getByRole('button', { name: 'Step into your workspace' }).click();
  await expect(page.getByRole('heading', { name: 'Good to see you, Maya.' })).toBeVisible();
  await expect(page.locator('.stat-card').filter({ hasText: 'Active goals' })).toContainText('27');
  await expect(page.locator('.stat-card').filter({ hasText: 'Approved activities' })).toContainText('10');
  await expect(page.getByRole('img', { name: /Daily checked and approved activities/ })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Recent activities' })).toBeVisible();
  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page.getByLabel('Email address')).toBeVisible();
});

test('goal library validates and persists create, edit, and delete', async ({ page }) => {
  await openAsTeacher(page, '/goals');
  await page.getByRole('button', { name: 'New goal', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'New approved goal' });
  await dialog.getByRole('button', { name: 'Save goal', exact: true }).click();
  await expect(dialog.getByText('Give it a clear title of at least 3 characters.')).toBeVisible();
  await dialog.getByLabel(/^Title/).fill('Plan the classroom supply pickup');
  await dialog.getByLabel('Skill description').fill('Choose a workable order for three classroom supply pickup steps and explain the plan.');
  await dialog.getByLabel('Approved success criteria').fill('Explain the first step and try the chosen plan during three practice opportunities.');
  await dialog.getByLabel('Approved accommodations').fill('Visual step cards\nExtra processing time');
  await dialog.getByLabel(/^Category/).fill('Workplace');
  await dialog.getByLabel('Target date').fill('2026-11-14');
  await dialog.getByRole('button', { name: 'Save goal', exact: true }).click();
  await expect(dialog).toBeHidden();
  await page.getByLabel('Search goals').fill('Plan the classroom supply pickup');
  await expect(page.getByRole('heading', { name: 'Plan the classroom supply pickup', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Edit Plan the classroom supply pickup', exact: true }).click();
  const edit = page.getByRole('dialog', { name: 'Edit approved goal' });
  await edit.getByLabel(/^Title/).fill('Plan the classroom supply pickup independently');
  await edit.getByRole('button', { name: 'Save goal', exact: true }).click();
  await expect(edit).toBeHidden();
  await expect(page.getByRole('heading', { name: 'Plan the classroom supply pickup independently', exact: true })).toBeVisible();
  await page.reload();
  await page.getByLabel('Search goals').fill('Plan the classroom supply pickup independently');
  await page.getByRole('button', { name: 'Delete Plan the classroom supply pickup independently', exact: true }).click();
  await confirmOpenDialog(page);
  await expect(page.getByRole('heading', { name: 'No matches just yet' })).toBeVisible();
});

test('activity library supports create, edit, archive, restore, delete, and an empty search', async ({ page }) => {
  await openAsTeacher(page, '/activities');
  await page.getByRole('button', { name: 'New activity', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'New activity' });
  await dialog.getByLabel(/^Title/).fill('Classroom supply pickup practice');
  await dialog.getByLabel('Approved goal', { exact: true }).selectOption('g01');
  await dialog.getByLabel('Worksheet / activity content').fill('Choose a first, next, and last step for gathering supplies. Explain your plan before trying it. Visual step cards and Extra processing time are available.');
  await dialog.getByLabel(/^Category/).fill('Workplace');
  await dialog.getByLabel('Target date').fill('2026-11-14');
  await dialog.getByRole('button', { name: 'Save activity', exact: true }).click();
  await expect(dialog).toBeHidden();
  await page.getByLabel('Search activities').fill('Classroom supply pickup practice');
  await expect(page.getByRole('heading', { name: 'Classroom supply pickup practice', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Edit Classroom supply pickup practice', exact: true }).click();
  const edit = page.getByRole('dialog', { name: 'Edit activity' });
  await edit.getByLabel('Worksheet / activity content').fill('Plan the supply pickup using three unnumbered task cards. Explain your chosen order before trying your plan. Keep Visual step cards and Extra processing time available.');
  await edit.getByRole('button', { name: 'Save activity', exact: true }).click();
  await expect(edit).toBeHidden();
  await page.getByRole('button', { name: 'Archive Classroom supply pickup practice', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Restore Classroom supply pickup practice', exact: true })).toBeEnabled();
  await page.getByLabel('Filter by status').selectOption('archived');
  await expect(page.getByRole('heading', { name: 'Classroom supply pickup practice', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Restore Classroom supply pickup practice', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'No matches just yet' })).toBeVisible();
  await page.getByLabel('Filter by status').selectOption('');
  await page.getByRole('button', { name: 'Delete Classroom supply pickup practice', exact: true }).click();
  await confirmOpenDialog(page);
  await expect(page.getByRole('heading', { name: 'No matches just yet' })).toBeVisible();
});

test('teacher checks evidence, restores a missing support, approves, and records learner practice', async ({ page }) => {
  await openAsTeacher(page, '/check?activity=a01');
  await expect(page.getByRole('heading', { name: 'Make the activity fit' })).toBeVisible();
  await page.getByRole('button', { name: 'Run check again', exact: true }).click();
  await expect(page.getByText('1. Gather the cleaning supplies', { exact: false }).last()).toBeVisible();
  await page.getByRole('button', { name: 'Create a revision draft', exact: true }).click();
  const content = page.getByLabel('Revision content');
  await expect(content).toHaveValue(/Your task: make your own plan/);
  const fullDraft = await content.inputValue();
  await content.fill(fullDraft.replace('Visual step cards', ''));
  await page.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Approve for practice', exact: true })).toBeDisabled();
  await expect(page.getByText(/Restore the approved accommodation\(s\): Visual step cards/)).toBeVisible();
  await content.fill(fullDraft);
  await page.getByRole('button', { name: 'Save changes', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Approve for practice', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Approve for practice', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'Ready for the learner?' })).toBeVisible();
  await confirmOpenDialog(page);
  await page.getByRole('link', { name: 'Open learner activity', exact: true }).click();
  await expect(page).toHaveURL(/\/try\/a01$/);
  await expect(page.getByRole('heading', { name: 'Practice a café opening routine', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Move step 2 up', exact: true }).click();
  await page.getByRole('button', { name: 'Submit my plan', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Your plan is saved', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Add observation', exact: true }).click();
  const observation = page.getByRole('dialog', { name: 'Teacher observation' });
  await observation.getByLabel('Observation', { exact: true }).fill('The learner chose a first card and explained how the materials were needed before starting.');
  await observation.getByLabel(/^Context/).fill('Quiet café practice area');
  await observation.getByRole('button', { name: 'Save observation', exact: true }).click();
  await expect(observation).toBeHidden();
  await expect(page.getByText('The learner chose a first card and explained how the materials were needed before starting.', { exact: true })).toBeVisible();
  await page.locator('article.observation-item').filter({ hasText: 'The learner chose a first card and explained how the materials were needed before starting.' }).getByRole('button', { name: 'Edit observation', exact: true }).click();
  await page.getByRole('dialog').getByLabel('Observation', { exact: true }).fill('The learner changed the first two cards after explaining which materials were needed.');
  await page.getByRole('dialog').getByRole('button', { name: 'Save observation', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeHidden();
  await expect(page.getByText('The learner changed the first two cards after explaining which materials were needed.', { exact: true })).toBeVisible();
  await page.locator('article.observation-item').filter({ hasText: 'The learner changed the first two cards after explaining which materials were needed.' }).getByRole('button', { name: 'Delete observation', exact: true }).click();
  await confirmOpenDialog(page);
  await expect(page.getByText('The learner changed the first two cards after explaining which materials were needed.', { exact: true })).toBeHidden();
  await page.goto('/history');
  await expect(page.getByRole('heading', { name: 'The story behind each activity', exact: true })).toBeVisible();
  await page.getByLabel('Search history').fill('Teacher approved this version');
  await expect(page.getByText('Teacher approved this version for learner practice. All approved accommodations retained.')).toBeVisible();
});

test('mobile and tablet navigation fit the viewport, dark mode persists, and keyboard focus is visible', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openAsTeacher(page);
  await expect(page.getByRole('heading', { name: 'Good to see you, Maya.' })).toBeVisible();
  const mobileNav = page.locator('nav.mobile-nav');
  await expect(mobileNav).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBeTruthy();
  await mobileNav.getByRole('link', { name: 'Goals', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Goals that guide the way' })).toBeVisible();
  await page.getByRole('button', { name: 'Switch to dark mode', exact: true }).click();
  await expect(page.locator('html')).toHaveClass(/dark/);
  await page.reload();
  await expect(page.locator('html')).toHaveClass(/dark/);
  await page.keyboard.press('Tab');
  const skip = page.getByRole('link', { name: 'Skip to content', exact: true });
  await expect(skip).toBeFocused();
  expect(await skip.evaluate(element => parseFloat(getComputedStyle(element).outlineWidth))).toBeGreaterThanOrEqual(2);
  await page.setViewportSize({ width: 768, height: 1024 });
  await expect(mobileNav).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBeTruthy();
});

test('a backend error offers a working retry instead of a broken dashboard', async ({ page }) => {
  await page.route('**/api/dashboard', route => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'The local demo backend is temporarily unavailable.' }) }));
  await openAsTeacher(page);
  await expect(page.getByRole('heading', { name: 'A small hiccup' })).toBeVisible();
  await expect(page.getByText('The local demo backend is temporarily unavailable.', { exact: true })).toBeVisible();
  await page.unroute('**/api/dashboard');
  await page.getByRole('button', { name: 'Try again', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Good to see you, Maya.' })).toBeVisible();
});
