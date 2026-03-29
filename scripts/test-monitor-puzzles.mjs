import { chromium } from 'playwright';
import { mkdirSync } from 'fs';

const browser = await chromium.launch();
mkdirSync('screenshots', { recursive: true });

const page = await browser.newPage({ viewport: { width: 375, height: 812 } });

try {
  // Play story #5 (existing)
  console.log('Playing existing story...');
  const res = await fetch('http://localhost:8741/api/stories/5/play', { method: 'POST' });
  const data = await res.json();
  console.log('Play response:', JSON.stringify(data).substring(0, 200));
  
  // Navigate to monitor
  await page.goto('http://localhost:5179/monitor', { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(2000);
  
  // Check for Puzzle Progress
  const puzzleProgress = await page.locator('text=Puzzle Progress').count();
  console.log(`Puzzle Progress visible: ${puzzleProgress > 0 ? 'YES' : 'NO'}`);
  
  // Check for Escape Chain
  const escapeChain = await page.locator('text=Escape Chain').count();
  console.log(`Escape Chain visible: ${escapeChain > 0 ? 'YES' : 'NO'}`);
  
  await page.screenshot({ path: 'screenshots/monitor-live-mobile.png', fullPage: true });
  
  // If puzzle progress exists, click to expand
  if (puzzleProgress > 0) {
    await page.locator('text=Puzzle Progress').click();
    await page.waitForTimeout(500);
    await page.screenshot({ path: 'screenshots/puzzle-expanded-mobile.png', fullPage: true });
    
    // Check for warmth indicators
    const cold = await page.locator('text=Cold').count();
    const warm = await page.locator('text=Warm').count();
    const hot = await page.locator('text=Hot').count();
    console.log(`Warmth indicators - Cold: ${cold}, Warm: ${warm}, Hot: ${hot}`);
    
    // Check for status badges
    const unsolved = await page.locator('text=Unsolved').count();
    const inProgress = await page.locator('text=In Progress').count();
    const solved = await page.locator('text=Solved').count();
    console.log(`Status badges - Unsolved: ${unsolved}, In Progress: ${inProgress}, Solved: ${solved}`);
    
    // Try clicking a puzzle card
    const puzzleCards = page.locator('[class*="rounded-xl"][class*="border"]');
    const cardCount = await puzzleCards.count();
    console.log(`Puzzle cards found: ${cardCount}`);
  }
  
  // Desktop test
  const dpage = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  await dpage.goto('http://localhost:5179/monitor', { waitUntil: 'networkidle', timeout: 15000 });
  await dpage.waitForTimeout(2000);
  
  const dpuzzleProgress = await dpage.locator('text=Puzzle Progress').count();
  console.log(`\nDesktop - Puzzle Progress visible: ${dpuzzleProgress > 0 ? 'YES' : 'NO'}`);
  
  if (dpuzzleProgress > 0) {
    await dpage.locator('text=Puzzle Progress').click();
    await dpage.waitForTimeout(500);
  }
  
  await dpage.screenshot({ path: 'screenshots/monitor-live-desktop.png', fullPage: true });
  await dpage.close();

} catch (err) {
  console.error('Error:', err.message);
} finally {
  await page.close();
  await browser.close();
}
