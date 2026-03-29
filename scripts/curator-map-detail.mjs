import { chromium } from 'playwright';
const browser = await chromium.launch();

// Desktop - expanded map, zoomed in
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
await page.goto('http://localhost:5173/monitor', { waitUntil: 'networkidle', timeout: 15000 });
await page.waitForTimeout(2000);

// Expand map 
const mapToggle = page.locator('text=Room Map').first();
await mapToggle.click();
await page.waitForTimeout(1500);

// Take a detailed screenshot focused on the map area
await page.screenshot({ path: 'screenshots/curator-recheck-map-detail-desktop.png' });
console.log('map detail: done');

// Click on a room to see detail popup
try {
  const roomNode = page.locator('.map-room-node').first();
  if (await roomNode.count() > 0) {
    await roomNode.click();
    await page.waitForTimeout(500);
    await page.screenshot({ path: 'screenshots/curator-recheck-room-popup-desktop.png' });
    console.log('room popup: done');
  }
} catch(e) { console.log('room click failed:', e.message); }

await page.close();
await browser.close();
