/**
 * screenshot.mjs — Take a single screenshot of a running UI page.
 *
 * Usage:
 *   node scripts/screenshot.mjs [url] [output] [width] [height]
 *
 * Examples:
 *   node scripts/screenshot.mjs http://localhost:5173 shot-mobile.png 375 812
 *   node scripts/screenshot.mjs http://localhost:5173/library screenshots/library-desktop.png 1280 800
 *
 * Defaults: url=http://localhost:5173, output=screenshot.png, width=375, height=812
 */

import { chromium } from 'playwright';

const url = process.argv[2] || 'http://localhost:5173';
const output = process.argv[3] || 'screenshot.png';
const width = parseInt(process.argv[4] || '375', 10);
const height = parseInt(process.argv[5] || '812', 10);

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width, height } });

try {
  await page.goto(url, { waitUntil: 'networkidle', timeout: 15000 });
  await page.screenshot({ path: output, fullPage: true });
  console.log(`Screenshot saved: ${output} (${width}x${height})`);
} catch (err) {
  console.error(`Failed to capture screenshot: ${err.message}`);
  process.exitCode = 1;
} finally {
  await browser.close();
}
