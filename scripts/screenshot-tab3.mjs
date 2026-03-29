import { chromium } from 'playwright';
import { mkdirSync } from 'fs';
import { dirname } from 'path';

const url = process.argv[2] || 'http://localhost:5179/creator';
const tabText = process.argv[3] || 'Validate';
const prefix = process.argv[4] || 'screenshots/tab';

const viewports = [
  { name: 'mobile',  width: 375,  height: 812  },
  { name: 'desktop', width: 1280, height: 800  },
];

const browser = await chromium.launch();

for (const vp of viewports) {
  const page = await browser.newPage({ viewport: { width: vp.width, height: vp.height } });
  const filename = `${prefix}-${vp.name}.png`;
  try { mkdirSync(dirname(filename), { recursive: true }); } catch {}

  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 15000 });
    const btn = page.locator(`button:has-text("${tabText}")`).first();
    await btn.click();
    await page.waitForTimeout(500);
    await page.screenshot({ path: filename, fullPage: true });
    console.log(`${vp.name}: ${filename}`);
  } catch (err) {
    console.error(`${vp.name} FAILED: ${err.message}`);
  } finally {
    await page.close();
  }
}

await browser.close();
