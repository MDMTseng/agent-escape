/**
 * screenshot-suite.mjs — Take mobile + tablet + desktop screenshots in one go.
 *
 * Usage:
 *   node scripts/screenshot-suite.mjs [url] [prefix]
 *
 * Examples:
 *   node scripts/screenshot-suite.mjs http://localhost:5173 screenshots/home
 *     -> screenshots/home-mobile.png, screenshots/home-tablet.png, screenshots/home-desktop.png
 *
 *   node scripts/screenshot-suite.mjs http://localhost:5173/library screenshots/library
 *     -> screenshots/library-mobile.png, screenshots/library-tablet.png, screenshots/library-desktop.png
 *
 * Defaults: url=http://localhost:5173, prefix=screenshot
 */

import { chromium } from 'playwright';
import { dirname } from 'path';
import { mkdirSync } from 'fs';

const url = process.argv[2] || 'http://localhost:5173';
const prefix = process.argv[3] || 'screenshot';

const viewports = [
  { name: 'mobile',  width: 375,  height: 812  },
  { name: 'tablet',  width: 768,  height: 1024 },
  { name: 'desktop', width: 1280, height: 800  },
];

const browser = await chromium.launch();
let failed = false;

for (const vp of viewports) {
  const page = await browser.newPage({ viewport: { width: vp.width, height: vp.height } });
  const filename = `${prefix}-${vp.name}.png`;

  // Ensure the output directory exists
  try {
    mkdirSync(dirname(filename), { recursive: true });
  } catch {
    // directory already exists or filename has no directory component
  }

  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 15000 });
    await page.screenshot({ path: filename, fullPage: true });
    console.log(`${vp.name} (${vp.width}x${vp.height}): ${filename}`);
  } catch (err) {
    console.error(`${vp.name} FAILED: ${err.message}`);
    failed = true;
  } finally {
    await page.close();
  }
}

await browser.close();

if (failed) {
  process.exitCode = 1;
}
