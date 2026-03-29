import { chromium } from 'playwright';
import { mkdirSync } from 'fs';

const browser = await chromium.launch();
mkdirSync('screenshots', { recursive: true });

const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });

try {
  await page.goto('http://localhost:5179/creator', { waitUntil: 'networkidle', timeout: 15000 });
  
  // First select a theme on Story tab
  console.log('Selecting a theme...');
  const themeCard = page.locator('text=Gothic Manor').first();
  await themeCard.click();
  await page.waitForTimeout(300);
  
  // Go to Validate tab
  await page.locator('button:has-text("Validate")').first().click();
  await page.waitForTimeout(300);
  
  // Click Save Scene
  console.log('Clicking Save Scene...');
  const saveBtn = page.locator('button:has-text("Save Scene")');
  await saveBtn.click();
  
  // Wait longer for server response
  await page.waitForTimeout(8000);
  
  // Check result
  const bodyText = await page.locator('body').textContent();
  if (bodyText.includes('saved successfully')) {
    console.log('SAVE: SUCCESS');
  } else if (bodyText.includes('Failed') || bodyText.includes('error')) {
    console.log('SAVE: FAILED');
    // Find the error message
    const errorEl = page.locator('.text-danger, [class*="danger"]');
    const errorTexts = await errorEl.allTextContents();
    console.log('Error messages:', errorTexts.join(', '));
  } else {
    console.log('SAVE: UNKNOWN STATE');
  }
  
  await page.screenshot({ path: 'screenshots/save-result-desktop.png', fullPage: true });
  
  // Check if Saved label appeared on button
  const savedBtn = await page.locator('button:has-text("Saved")').count();
  console.log(`"Saved" button visible: ${savedBtn > 0}`);
  
} catch (err) {
  console.error('Error:', err.message);
} finally {
  await page.close();
  await browser.close();
}
