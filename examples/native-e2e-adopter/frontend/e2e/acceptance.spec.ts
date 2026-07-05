// Worked example — the adopter's real Playwright spec the MANAGED external_test_runner runs.
// The framework starts the app (app_start_cmd + readiness poll), runs `npx playwright test
// <this spec> --reporter=json`, captures exit code + JSON report + trace + screenshots + logs,
// verifies framework-owned provenance, and cleans up — NO human runs it.
//
// Each test title carries a `@crit:<criterion_id>` tag binding it to a SIGNED functional-checklist
// criterion (the other binding channel is charter.tooling.e2e.criterion_map). Every signed criterion
// MUST have a bound test — an unmapped criterion is a pre-publication contract HALT.
//
// Secrets are NAMED env references (env:AIJP_TEST_USER / env:AIJP_TEST_PASS) the adopter sets
// out-of-band in a gitignored .env.local — never inlined here.

import { test, expect } from '@playwright/test';

const USER = process.env.AIJP_TEST_USER!;
const PASS = process.env.AIJP_TEST_PASS!;

async function login(page) {
  await page.goto('/login');
  await page.fill('#username', USER);
  await page.fill('#password', PASS);
  await page.click('button[type=submit]');
}

test('dashboard greets the user by name @crit:shows_welcome', async ({ page }) => {
  await login(page);
  await expect(page.locator('#welcome')).toContainText(USER);
});

test('keyword search returns matching jobs @crit:job_search_returns_results', async ({ page }) => {
  await login(page);
  await page.goto('/jobs');
  await page.fill('#search', 'engineer');
  await page.click('#search-submit');
  await expect(page.locator('.job-card')).not.toHaveCount(0);
});
