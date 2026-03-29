import { chromium } from 'playwright';
import { mkdirSync } from 'fs';
import { dirname } from 'path';

const url = process.argv[2] || 'http://localhost:5179/creator';
const tabIndex = parseInt(process.argv[3] || '3'); // 0-based
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
    // Dump the tab texts for debug
    const tabs = await page.locator('button').allTextContents();
    const matching = tabs.filter(t => t.includes('Agent') || t.includes('Validate') || t.includes('Story') || t.includes('Room') || t.includes('Puzzle'));
    console.log(`${vp.name} tabs found:`, matching.join(' | '));
    
    // Click tab by role or by finding buttons with specific text
    const agentBtn = page.locator('button:has-text("Agents")').first();
    if (await agentBtn.isVisible()) {
      await agentBtn.click();
      await page.waitForTimeout(500);
    }
    await page.screenshot({ path: filename, fullPage: true });
    console.log(`${vp.name}: ${filename}`);
  } catch (err) {
    console.error(`${vp.name} FAILED: ${err.message}`);
  } finally {
    await page.close();
  }
}

await browser.close();
