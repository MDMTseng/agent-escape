import { chromium } from 'playwright';
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
await page.goto('http://localhost:5173/monitor', { waitUntil: 'networkidle', timeout: 15000 });
await page.waitForTimeout(2000);

// Get all button aria labels
const buttons = await page.locator('button').all();
for (const btn of buttons) {
  const label = await btn.getAttribute('aria-label');
  const text = (await btn.textContent()).trim().slice(0, 40);
  if (label || text) console.log(`  [${label || 'no-label'}] "${text}"`);
}

// Check escape chain text
const chainText = await page.locator('text=/\d+ \/ \d+/').first().textContent().catch(() => 'not found');
console.log('Chain text:', chainText);

await page.close();
await browser.close();
