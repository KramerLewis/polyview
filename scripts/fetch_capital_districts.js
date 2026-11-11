// Fetch LEAP's "capital projects by legislative district" reports (SSRS report
// viewers on fiscal.wa.gov) for every district, as CSV. The reports need
// JavaScript, so this drives a headless browser. DECISIONS D-035.
//
// Usage:
//   node scripts/fetch_capital_districts.js <out-dir> [preset]
// Presets:
//   bien  (default) CapitalProjectListDistrictBien.aspx: Version=1 (latest
//         enacted biennial budget), District, Fund=TOT-B
//   supp  CapitalProjectListDistrictCompareSupp.aspx: Version 1=1 (latest
//         enacted supplemental), District, Version 2=2 (must differ), Fund=TOT-B,
//         Format=2 ("Biennial + Supp = Revised": the full current list)
// Env: DISTRICTS=1,2,3 to fetch only some districts.
// Output: <out-dir>/ld<NN>.csv plus versions.json (what was selected).
// Requires: npm package "playwright" with Chromium.
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const PRESETS = {
  bien: { page: 'CapitalProjectListDistrictBien.aspx', district: 1, params: { 0: '1', 2: '1' } },
  // Version 2 must differ from Version 1: with both set to the same version the
  // report double-counts every amount (DECISIONS D-040). Use the "Version 1" columns.
  supp: { page: 'CapitalProjectListDistrictCompareSupp.aspx', district: 1,
          params: { 0: '1', 2: '2', 3: '1', 4: '2' } },
};
const out = process.argv[2];
const preset = { ...PRESETS[process.argv[3] || 'bien'] };
// PARAMS='{"4":"1"}' overrides individual report parameters (by position).
if (process.env.PARAMS) preset.params = { ...preset.params, ...JSON.parse(process.env.PARAMS) };
const URL = `https://fiscal.wa.gov/StateBudgets/${preset.page}`;

(async () => {
  fs.mkdirSync(out, { recursive: true });
  const proxy = process.env.HTTPS_PROXY ? { server: process.env.HTTPS_PROXY } : undefined;
  const browser = await chromium.launch(proxy ? { proxy } : {});
  const p = await browser.newPage();
  const sel = (i) => p.locator('select[name$="ddValue"]').nth(i);
  const enabled = (i) => p.waitForFunction((n) => {
    const s = document.querySelectorAll('select[name$="ddValue"]')[n];
    return s && !s.disabled;
  }, i, { timeout: 90000 });
  const choose = async (i, v) => { await enabled(i); await sel(i).selectOption(v); await p.waitForLoadState('networkidle'); };
  const label = (i) => sel(i).evaluate((s) => s.options[s.selectedIndex].text.replace(/\s+/g, ' ').trim());

  await p.goto(URL, { timeout: 120000 });
  await enabled(preset.district);
  const districts = (await sel(preset.district).locator('option').evaluateAll((os) => os.map((o) => o.value)))
    .filter((v) => /^\d+$/.test(v));  // '1'..'49'; placeholders use GUIDs
  const only = (process.env.DISTRICTS || '').split(',').filter(Boolean);
  let meta = null;

  for (const d of districts) {
    if (only.length && !only.includes(d)) continue;
    for (let attempt = 1; ; attempt++) {
      try { await fetchDistrict(d); break; } catch (e) {
        console.error(`district ${d} attempt ${attempt} failed: ${e.message.split('\n')[0]}`);
        if (attempt >= 3) throw e;
        await p.goto(URL, { timeout: 120000 });
      }
    }
  }
  await browser.close();

  async function fetchDistrict(d) {
    const order = Object.keys(preset.params).map(Number).concat([preset.district]).sort((a, b) => a - b);
    for (const i of order) await choose(i, i === preset.district ? d : preset.params[i]);
    if (!meta) {
      meta = { page: preset.page, fetched_at: new Date().toISOString(), params: {} };
      for (const i of order) if (i !== preset.district) meta.params[i] = await label(i);
      meta.selected = meta.params[0];
      fs.writeFileSync(path.join(out, 'versions.json'), JSON.stringify(meta, null, 1));
    }
    await p.click('input[type=submit][value="View Report"]');
    await p.waitForLoadState('networkidle');
    await p.waitForFunction(() => /"ExportUrlBase":"/.test(document.documentElement.innerHTML), null, { timeout: 120000 });
    const html = await p.content();
    const base = html.match(/"ExportUrlBase":"([^"]+)"/)[1].replace(/\\u0026/g, '&');
    const resp = await p.request.get('https://fiscal.wa.gov' + base + 'CSV', { timeout: 120000 });
    const body = await resp.text();
    if (resp.status() !== 200 || !body.includes('Legislative District')) throw new Error(`bad export (${resp.status()})`);
    fs.writeFileSync(path.join(out, `ld${String(d).padStart(2, '0')}.csv`), body);
    console.log(`district ${d}: ${resp.status()} ${body.length} bytes`);
  }
})().catch((e) => { console.error('ERR', e); process.exit(1); });
