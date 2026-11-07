// Fetch LEAP's "capital projects by legislative district" report (an SSRS
// report viewer on fiscal.wa.gov) for every district, as CSV.
// The report needs JavaScript, so this drives a headless browser.
//
// Usage: node scripts/fetch_capital_districts.js <out-dir> [version-index] [report-page]
//   version-index: position in the report's "Version" list (1 = most recent enacted)
// Output: <out-dir>/ld<NN>.csv plus versions.json (the version labels seen).
// Requires: npm package "playwright" with Chromium.
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const out = process.argv[2];
const version = process.argv[3] || '1';
const page = process.argv[4] || 'CapitalProjectListDistrictBien.aspx';
const URL = `https://fiscal.wa.gov/StateBudgets/${page}`;

(async () => {
  fs.mkdirSync(out, { recursive: true });
  const proxy = process.env.HTTPS_PROXY ? { server: process.env.HTTPS_PROXY } : undefined;
  const browser = await chromium.launch(proxy ? { proxy } : {});
  const p = await browser.newPage();
  await p.goto(URL, { timeout: 120000 });
  const sel = (i) => p.locator('select[name$="ddValue"]').nth(i);
  const enabled = (i) => p.waitForFunction((n) => {
    const s = document.querySelectorAll('select[name$="ddValue"]')[n];
    return s && !s.disabled;
  }, i, { timeout: 90000 });

  await enabled(0);
  const versions = await sel(0).locator('option').allInnerTexts();
  await sel(0).selectOption(version);
  const selected = await sel(0).evaluate((s) => s.options[s.selectedIndex].text);
  fs.writeFileSync(path.join(out, 'versions.json'), JSON.stringify(
    { page, value: version, selected: selected.replace(/\s+/g, ' ').trim(),
      fetched_at: new Date().toISOString(), versions }, null, 1));
  await p.waitForLoadState('networkidle');
  await enabled(1);
  // Option values are '1'..'49'; the placeholder's value is a GUID.
  const districts = (await sel(1).locator('option').evaluateAll((os) => os.map((o) => o.value)))
    .filter((v) => /^\d+$/.test(v));
  const only = (process.env.DISTRICTS || '').split(',').filter(Boolean);

  for (const d of districts) {
    if (only.length && !only.includes(d)) continue;
    for (let attempt = 1; ; attempt++) {
      try { await fetchDistrict(d); break; } catch (e) {
        console.error(`district ${d} attempt ${attempt} failed: ${e.message.split('\n')[0]}`);
        if (attempt >= 3) throw e;
        await p.goto(URL, { timeout: 120000 });
        await enabled(0); await sel(0).selectOption(version); await p.waitForLoadState('networkidle');
      }
    }
  }
  await browser.close();

  async function fetchDistrict(d) {
    await enabled(1);
    await sel(1).selectOption(d);
    await p.waitForLoadState('networkidle');
    await enabled(2);
    await sel(2).selectOption('1'); // Total Budgeted Funds (TOT-B)
    await p.waitForLoadState('networkidle');
    await p.click('input[type=submit][value="View Report"]');
    await p.waitForLoadState('networkidle');
    await p.waitForFunction(() => /"ExportUrlBase":"/.test(document.documentElement.innerHTML), null, { timeout: 120000 });
    const html = await p.content();
    const base = html.match(/"ExportUrlBase":"([^"]+)"/)[1].replace(/\\u0026/g, '&');
    const resp = await p.request.get('https://fiscal.wa.gov' + base + 'CSV', { timeout: 120000 });
    const body = await resp.text();
    fs.writeFileSync(path.join(out, `ld${String(d).padStart(2, '0')}.csv`), body);
    if (resp.status() !== 200 || !body.includes('Legislative District')) throw new Error(`bad export (${resp.status()})`);
    console.log(`district ${d}: ${resp.status()} ${body.length} bytes`);
  }
})().catch((e) => { console.error('ERR', e); process.exit(1); });
