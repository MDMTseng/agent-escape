import { chromium } from 'playwright';

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 375, height: 812 } });

try {
  await page.goto('http://localhost:5179/monitor', { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(2000);
  
  // Find all buttons and their labels
  const buttons = await page.locator('button').all();
  for (const btn of buttons) {
    const label = await btn.getAttribute('aria-label');
    const text = await btn.textContent();
    const visible = await btn.isVisible();
    if (visible && (label || text.trim())) {
      console.log(`Button: label="${label}", text="${text.trim().substring(0,30)}"`);
    }
  }
  
} catch (err) {
  console.error('Error:', err.message);
} finally {
  await page.close();
  await browser.close();
}
