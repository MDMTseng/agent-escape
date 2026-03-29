import { chromium } from 'playwright';
const browser = await chromium.launch();

// Desktop - open load panel with saves
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
await page.goto('http://localhost:5173/monitor', { waitUntil: 'networkidle', timeout: 15000 });
await page.waitForTimeout(2000);

// Open load panel
const loadBtn = page.locator('button[aria-label="Load game"]');
await loadBtn.click();
await page.waitForTimeout(2000); // wait for saves to load
await page.screenshot({ path: 'screenshots/curator-recheck-load-with-saves-desktop.png', fullPage: true });
console.log('load with saves desktop: done');

// Check console errors
page.on('console', msg => {
  if (msg.type() === 'error') console.log('CONSOLE ERROR:', msg.text());
});

await page.close();

// Mobile load
const mobile = await browser.newPage({ viewport: { width: 375, height: 812 } });
await mobile.goto('http://localhost:5173/monitor', { waitUntil: 'networkidle', timeout: 15000 });
await mobile.waitForTimeout(2000);

const mobileLoadBtn = mobile.locator('button[aria-label="Load game"]');
await mobileLoadBtn.click();
await mobile.waitForTimeout(2000);
await mobile.screenshot({ path: 'screenshots/curator-recheck-load-with-saves-mobile.png', fullPage: true });
console.log('load with saves mobile: done');

await mobile.close();
await browser.close();
