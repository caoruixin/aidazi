/**
 * Phase-5 canary — a REAL Node/Playwright spec-runner (the adopter's managed `runner_argv`).
 *
 * The framework's `external_test_runner` executor spawns THIS as a managed subprocess (shell=false),
 * having already: started the app + polled readiness; written `executor-config.json` (with the
 * concrete `base_url`) into the evidence dir; set `PLAYWRIGHT_JSON_OUTPUT_NAME` (where to write the
 * report) + `--output <dir>` (where artifacts land) + the framework `AIDAZI_E2E_INVOCATION_NONCE`.
 *
 * This runner launches REAL headless chromium (via the `playwright` core resolved from the repo's
 * node_modules), drives two criterion-tagged tests against the started app, captures a REAL trace.zip
 * + per-test screenshots, emits a Playwright-JSON report, and exits 0 iff every test passed (non-zero
 * on any failure — the exit/report agreement the provenance gate checks). It NEVER fabricates: a
 * failing assertion is a real `failed` result from a real page load.
 *
 * Criteria (bound to the signed checklist via `@crit:<id>` in the test title):
 *   - home_loads : GET /        -> #home text must be "OK"   (a stable pass)
 *   - result_ok  : GET /result  -> #result text must be "OK" (flips BROKEN->OK when the Dev fix flag
 *                                   is written; this is what §1.7-G remediation drives to pass)
 */
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright'); // resolved from <repo>/node_modules/playwright

function argOutputDir() {
  const i = process.argv.indexOf('--output');
  if (i !== -1 && process.argv[i + 1]) return process.argv[i + 1];
  return null;
}

async function main() {
  const reportPath = process.env.PLAYWRIGHT_JSON_OUTPUT_NAME;
  if (!reportPath) throw new Error('PLAYWRIGHT_JSON_OUTPUT_NAME not set by the framework');
  const evidenceDir = path.dirname(reportPath);
  const outDir = argOutputDir() || path.join(evidenceDir, 'test-results');
  fs.mkdirSync(outDir, { recursive: true });

  // The framework wrote the concrete runtime contract (base_url incl. the allocated port).
  const cfg = JSON.parse(fs.readFileSync(path.join(evidenceDir, 'executor-config.json'), 'utf-8'));
  const baseUrl = cfg.base_url;
  if (!baseUrl) throw new Error('no base_url in executor-config.json');

  const cases = [
    { crit: 'home_loads', url: '/', sel: '#home' },
    { crit: 'result_ok', url: '/result', sel: '#result' },
  ];

  const browser = await chromium.launch();
  const context = await browser.newContext();
  await context.tracing.start({ screenshots: true, snapshots: true });
  const specs = [];
  let anyFailed = false;

  for (const c of cases) {
    const page = await context.newPage();
    let status = 'passed';
    let errorMsg = null;
    try {
      await page.goto(baseUrl + c.url, { waitUntil: 'load', timeout: 15000 });
      const txt = ((await page.textContent(c.sel)) || '').trim();
      if (txt !== 'OK') { status = 'failed'; errorMsg = `expected OK at ${c.sel}, got ${JSON.stringify(txt)}`; }
    } catch (e) {
      status = 'failed';
      errorMsg = String(e && e.message || e);
    }
    const shot = path.join(outDir, `${c.crit}.png`);
    try { await page.screenshot({ path: shot }); } catch (_) { /* keep going */ }
    await page.close();
    if (status !== 'passed') anyFailed = true;
    const result = { status, attachments: [{ name: 'screenshot', path: shot }] };
    if (errorMsg) result.error = { message: errorMsg };
    specs.push({ title: `${c.crit} @crit:${c.crit}`, ok: status === 'passed', tags: [`crit:${c.crit}`],
      tests: [{ results: [result] }] });
  }

  const tracePath = path.join(outDir, 'trace.zip');
  await context.tracing.stop({ path: tracePath });
  await browser.close();

  // attach the shared trace to every spec so each criterion binds a concrete real-browser artifact
  for (const sp of specs) sp.tests[0].results[0].attachments.push({ name: 'trace', path: tracePath });

  const report = { suites: [{ title: 'acceptance.spec', specs }] };
  fs.writeFileSync(reportPath, JSON.stringify(report));
  process.exit(anyFailed ? 1 : 0);
}

main().catch((e) => { console.error(e); process.exit(2); });
