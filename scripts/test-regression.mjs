import { chromium } from 'playwright';

const browser = await chromium.launch();
const errors = [];

// Quick regression check of key P0 features
const page = await browser.newPage({ viewport: { width: 375, height: 812 } });
page.on('console', msg => { if (msg.type() === 'error') errors.push(`${page.url()}: ${msg.text()}`); });

try {
  // P0-004: Library page loads
  console.log('Checking Library...');
  await page.goto('http://localhost:5179/', { waitUntil: 'networkidle', timeout: 15000 });
  const libraryCards = await page.locator('[class*="rounded"]').count();
  console.log(`  Library loaded, elements: ${libraryCards}`);
  
  // P0-006/007/008/009: Monitor page
  console.log('Checking Monitor...');
  await page.goto('http://localhost:5179/monitor', { waitUntil: 'networkidle', timeout: 15000 });
  const agentStrip = await page.locator('text=Alice').count() + await page.locator('text=Bob').count();
  console.log(`  Agents visible: ${agentStrip > 0 ? 'YES' : 'NO'}`);
  
  const simControls = await page.locator('button[aria-label="Play"], button[aria-label="Resume"]').count();
  console.log(`  Sim controls: ${simControls > 0 ? 'YES' : 'NO'}`);
  
  // P1-001/002/003: Creator tabs
  console.log('Checking Creator...');
  await page.goto('http://localhost:5179/creator', { waitUntil: 'networkidle', timeout: 15000 });
  
  const tabs = await page.locator('button').allTextContents();
  const tabNames = tabs.filter(t => ['Story', 'Rooms', 'Puzzles', 'Agents', 'Validate'].some(n => t.includes(n)));
  console.log(`  Creator tabs: ${tabNames.join(', ')}`);
  
  // Check Story tab content
  const themeCards = await page.locator('text=Gothic Manor').count();
  console.log(`  Theme cards visible: ${themeCards > 0 ? 'YES' : 'NO'}`);
  
  // Check Rooms tab
  await page.locator('button:has-text("Rooms")').first().click();
  await page.waitForTimeout(300);
  const roomsContent = await page.locator('text=Add Room').count();
  console.log(`  Rooms tab loaded: ${roomsContent > 0 ? 'YES' : 'NO'}`);
  
  // Check Puzzles tab
  await page.locator('button:has-text("Puzzles")').first().click();
  await page.waitForTimeout(300);
  const puzzlesContent = await page.locator('text=No puzzles yet').count() + await page.locator('text=Add Puzzle').count();
  console.log(`  Puzzles tab loaded: ${puzzlesContent > 0 ? 'YES' : 'NO'}`);
  
  console.log(`\nConsole errors: ${errors.length}`);
  errors.forEach(e => console.log(`  - ${e}`));
  
} catch (err) {
  console.error('Error:', err.message);
} finally {
  await page.close();
  await browser.close();
}
