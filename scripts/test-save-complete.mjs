import { chromium } from 'playwright';
import { mkdirSync } from 'fs';

const browser = await chromium.launch();
mkdirSync('screenshots', { recursive: true });

const page = await browser.newPage({ viewport: { width: 375, height: 812 } });

try {
  await page.goto('http://localhost:5179/creator', { waitUntil: 'networkidle', timeout: 15000 });
  
  // Select theme first
  const themeCard = page.locator('button:has-text("Gothic Manor"), [class*="border-gold"]').first();
  await themeCard.click();
  await page.waitForTimeout(300);
  
  // Go to validate tab
  await page.locator('button:has-text("Validate")').first().click();
  await page.waitForTimeout(300);
  
  // Click Save Scene and wait long enough
  console.log('Saving...');
  await page.locator('button:has-text("Save Scene")').click();
  
  // Wait for either success or failure (up to 30 seconds)
  try {
    await page.waitForSelector('text=saved successfully', { timeout: 30000 });
    console.log('SAVE: SUCCESS');
    await page.screenshot({ path: 'screenshots/save-success-mobile.png', fullPage: true });
  } catch {
    const hasError = await page.locator('text=Failed').count();
    const hasServerError = await page.locator('text=Server error').count();
    console.log(`SAVE: Timeout or error. Failed: ${hasError > 0}, Server error: ${hasServerError > 0}`);
    await page.screenshot({ path: 'screenshots/save-timeout-mobile.png', fullPage: true });
  }
  
  // Test Play Scene button
  const playBtn = page.locator('button:has-text("Play Scene")');
  const playDisabled = await playBtn.isDisabled();
  console.log(`Play disabled: ${playDisabled}`);
  
} catch (err) {
  console.error('Error:', err.message);
} finally {
  await page.close();
  await browser.close();
}
