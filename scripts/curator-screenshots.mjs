import { chromium } from 'playwright';
import { mkdirSync } from 'fs';

const prefix = 'screenshots/curator-recheck';
mkdirSync('screenshots', { recursive: true });

const browser = await chromium.launch();

// Desktop screenshots with interactions
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
await page.goto('http://localhost:5173/monitor', { waitUntil: 'networkidle', timeout: 15000 });
await page.waitForTimeout(2000);

// Step the simulation to generate narrative data + thought bubbles
try {
  // Click the Step button (the forward arrow)
  const stepBtn = page.locator('button[aria-label="Step one tick"]');
  if (await stepBtn.count() > 0) {
    await stepBtn.click();
    await page.waitForTimeout(5000); // wait for tick to complete
    await page.screenshot({ path: `${prefix}-after-step-desktop.png`, fullPage: true });
    console.log('after-step desktop: done');
  } else {
    // Try clicking the step icon button (the SkipForward/Next icon)
    const allBtns = page.locator('button');
    const count = await allBtns.count();
    for (let i = 0; i < count; i++) {
      const text = await allBtns.nth(i).textContent();
      const label = await allBtns.nth(i).getAttribute('aria-label');
      if (label && label.includes('tep')) {
        await allBtns.nth(i).click();
        break;
      }
    }
    await page.waitForTimeout(5000);
    await page.screenshot({ path: `${prefix}-after-step-desktop.png`, fullPage: true });
    console.log('after-step desktop (fallback): done');
  }
} catch(e) { console.log('step failed:', e.message); }

// Expand Room Map
try {
  const mapToggle = page.locator('text=Room Map').first();
  if (await mapToggle.count() > 0) {
    await mapToggle.click();
    await page.waitForTimeout(1500); // wait for React Flow to render + entrance animations
    await page.screenshot({ path: `${prefix}-map-expanded-desktop.png`, fullPage: true });
    console.log('map expanded desktop: done');
  }
} catch(e) { console.log('map expand failed:', e.message); }

// Open Save dialog
try {
  const saveBtn = page.locator('button[aria-label="Save game"]');
  if (await saveBtn.count() > 0) {
    await saveBtn.click();
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${prefix}-save-dialog-desktop.png`, fullPage: true });
    console.log('save dialog desktop: done');
    // Close it
    await page.locator('button[aria-label="Close"]').first().click();
    await page.waitForTimeout(300);
  }
} catch(e) { console.log('save dialog failed:', e.message); }

// Open Load panel
try {
  const loadBtn = page.locator('button[aria-label="Load game"]');
  if (await loadBtn.count() > 0) {
    await loadBtn.click();
    await page.waitForTimeout(1000);
    await page.screenshot({ path: `${prefix}-load-panel-desktop.png`, fullPage: true });
    console.log('load panel desktop: done');
    await page.locator('button[aria-label="Close"]').first().click();
    await page.waitForTimeout(300);
  }
} catch(e) { console.log('load panel failed:', e.message); }

await page.close();

// Mobile screenshots with interactions
const mobile = await browser.newPage({ viewport: { width: 375, height: 812 } });
await mobile.goto('http://localhost:5173/monitor', { waitUntil: 'networkidle', timeout: 15000 });
await mobile.waitForTimeout(2000);

// Step on mobile
try {
  const stepBtn = mobile.locator('button[aria-label="Step one tick"]');
  if (await stepBtn.count() > 0) {
    await stepBtn.click();
    await mobile.waitForTimeout(5000);
  }
  await mobile.screenshot({ path: `${prefix}-after-step-mobile.png`, fullPage: true });
  console.log('after-step mobile: done');
} catch(e) { console.log('mobile step failed:', e.message); }

// Mobile map FAB
try {
  const mapFab = mobile.locator('button[aria-label="Open room map"]');
  if (await mapFab.count() > 0) {
    await mapFab.click();
    await mobile.waitForTimeout(1500);
    await mobile.screenshot({ path: `${prefix}-map-mobile.png`, fullPage: true });
    console.log('map mobile: done');
    await mobile.locator('button[aria-label="Close map"]').click();
    await mobile.waitForTimeout(300);
  }
} catch(e) { console.log('mobile map failed:', e.message); }

// Mobile save dialog
try {
  const saveBtn = mobile.locator('button[aria-label="Save game"]');
  if (await saveBtn.count() > 0) {
    await saveBtn.click();
    await mobile.waitForTimeout(500);
    await mobile.screenshot({ path: `${prefix}-save-mobile.png`, fullPage: true });
    console.log('save mobile: done');
    await mobile.locator('.fixed.inset-0').first().click({ position: { x: 10, y: 10 } });
    await mobile.waitForTimeout(300);
  }
} catch(e) { console.log('mobile save failed:', e.message); }

// Mobile load panel
try {
  const loadBtn = mobile.locator('button[aria-label="Load game"]');
  if (await loadBtn.count() > 0) {
    await loadBtn.click();
    await mobile.waitForTimeout(1000);
    await mobile.screenshot({ path: `${prefix}-load-mobile.png`, fullPage: true });
    console.log('load mobile: done');
  }
} catch(e) { console.log('mobile load failed:', e.message); }

await mobile.close();
await browser.close();
console.log('All curator screenshots complete');
