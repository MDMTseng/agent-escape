import { chromium } from 'playwright';
import { mkdirSync } from 'fs';

const browser = await chromium.launch();
mkdirSync('screenshots', { recursive: true });

const page = await browser.newPage({ viewport: { width: 375, height: 812 } });

try {
  await page.goto('http://localhost:5179/monitor', { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(1500);
  
  // Expand Puzzle Progress
  const pp = page.locator('text=Puzzle Progress');
  if (await pp.count() > 0) {
    await pp.click();
    await page.waitForTimeout(500);
    
    // Click first puzzle card to expand it
    const firstCard = page.locator('button:has-text("Examine")').first();
    if (await firstCard.count() > 0) {
      await firstCard.click();
      await page.waitForTimeout(300);
      await page.screenshot({ path: 'screenshots/puzzle-card-expanded-mobile.png', fullPage: true });
      console.log('Puzzle card expanded screenshot taken');
      
      // Check for entity list
      const entityList = await page.locator('text=Room Entities').count();
      console.log(`Room Entities section visible: ${entityList > 0 ? 'YES' : 'NO'}`);
      
      // Check for step details
      const actionLabel = await page.locator('text=Action:').count();
      const targetLabel = await page.locator('text=Target:').count();
      console.log(`Action label: ${actionLabel > 0}, Target label: ${targetLabel > 0}`);
    }
  }
  
  // Now test on desktop
  const dpage = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  await dpage.goto('http://localhost:5179/monitor', { waitUntil: 'networkidle', timeout: 15000 });
  await dpage.waitForTimeout(1500);
  
  const dpp = dpage.locator('text=Puzzle Progress');
  if (await dpp.count() > 0) {
    await dpp.click();
    await dpage.waitForTimeout(500);
    
    const firstCard = dpage.locator('button:has-text("Examine")').first();
    if (await firstCard.count() > 0) {
      await firstCard.click();
      await dpage.waitForTimeout(300);
      await dpage.screenshot({ path: 'screenshots/puzzle-card-expanded-desktop.png', fullPage: true });
      console.log('Desktop puzzle card expanded screenshot taken');
    }
  }
  
  await dpage.close();
  
} catch (err) {
  console.error('Error:', err.message);
} finally {
  await page.close();
  await browser.close();
}
