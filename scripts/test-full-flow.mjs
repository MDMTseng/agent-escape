import { chromium } from 'playwright';
import { mkdirSync } from 'fs';

const browser = await chromium.launch();
mkdirSync('screenshots', { recursive: true });

// Test P1-005: Save Scene
console.log('=== P1-005: Save Scene ===');
{
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  await page.goto('http://localhost:5179/creator', { waitUntil: 'networkidle', timeout: 15000 });
  
  // Go to Validate tab
  await page.locator('button:has-text("Validate")').first().click();
  await page.waitForTimeout(300);
  
  // Click Save Scene (even with failures)
  console.log('Clicking Save Scene...');
  const saveBtn = page.locator('button:has-text("Save Scene")');
  const saveDisabled = await saveBtn.isDisabled();
  console.log(`  Save button disabled: ${saveDisabled}`);
  
  // Save should work even with validation failures (just creating the story)
  await saveBtn.click();
  await page.waitForTimeout(3000);
  
  // Check for success or error
  const successMsg = await page.locator('text=saved successfully').count();
  const errorMsg = await page.locator('text=Server error').count();
  const failedMsg = await page.locator('text=Failed').count();
  console.log(`  Success: ${successMsg > 0}, Server error: ${errorMsg > 0}, Failed: ${failedMsg > 0}`);
  
  await page.screenshot({ path: 'screenshots/validate-after-save-desktop.png', fullPage: true });
  
  // Check Play Scene button state after save
  const playBtn = page.locator('button:has-text("Play Scene")');
  const playDisabled = await playBtn.isDisabled();
  console.log(`  Play button disabled after save: ${playDisabled}`);
  
  await page.close();
}

// Test P1-006: Puzzle Progress on Monitor
console.log('\n=== P1-006: Puzzle Progress Dashboard ===');
{
  const page = await browser.newPage({ viewport: { width: 375, height: 812 } });
  
  // First create and play a game to get data
  console.log('Creating a game via Quick Play...');
  await page.goto('http://localhost:5179/', { waitUntil: 'networkidle', timeout: 15000 });
  
  // Try Quick Play
  const quickPlayBtn = page.locator('button:has-text("Quick Play")');
  const qpCount = await quickPlayBtn.count();
  console.log(`  Quick Play button found: ${qpCount > 0 ? 'YES' : 'NO'}`);
  
  if (qpCount > 0) {
    await quickPlayBtn.click();
    await page.waitForTimeout(5000); // Wait for story generation
    
    const onMonitor = page.url().includes('/monitor');
    console.log(`  Navigated to monitor: ${onMonitor}`);
    
    // Look for Puzzle Progress panel
    const puzzleProgress = await page.locator('text=Puzzle Progress').count();
    console.log(`  Puzzle Progress visible: ${puzzleProgress > 0 ? 'YES' : 'NO'}`);
    
    // Check for escape chain data
    const escapeChain = await page.locator('text=Escape Chain').count();
    console.log(`  Escape Chain visible: ${escapeChain > 0 ? 'YES' : 'NO'}`);
    
    await page.screenshot({ path: 'screenshots/monitor-with-puzzle-progress-mobile.png', fullPage: true });
    
    // Try clicking Puzzle Progress to expand
    if (puzzleProgress > 0) {
      await page.locator('text=Puzzle Progress').click();
      await page.waitForTimeout(300);
      await page.screenshot({ path: 'screenshots/puzzle-progress-expanded-mobile.png', fullPage: true });
    }
    
    // Run a few ticks to generate data
    console.log('Running simulation ticks...');
    const playBtn = page.locator('button[aria-label="Play"], button[aria-label="Resume"]');
    if (await playBtn.count() > 0) {
      await playBtn.first().click();
      await page.waitForTimeout(3000);
      // Pause
      const pauseBtn = page.locator('button[aria-label="Pause"]');
      if (await pauseBtn.count() > 0) {
        await pauseBtn.first().click();
      }
    }
    
    await page.screenshot({ path: 'screenshots/monitor-after-ticks-mobile.png', fullPage: true });
  }
  
  await page.close();
}

// Desktop test with agents expanded
console.log('\n=== Desktop: Agents with full form ===');
{
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  await page.goto('http://localhost:5179/creator', { waitUntil: 'networkidle', timeout: 15000 });
  
  // Agents tab
  await page.locator('button:has-text("Agents")').first().click();
  await page.waitForTimeout(300);
  
  // Add Detective
  await page.locator('button:has-text("The Detective")').click();
  await page.waitForTimeout(200);
  
  // Add Helper
  await page.locator('button:has-text("The Helper")').click();
  await page.waitForTimeout(200);
  
  // Expand first agent
  await page.locator('[aria-label="Expand"]').first().click();
  await page.waitForTimeout(300);
  
  await page.screenshot({ path: 'screenshots/agents-desktop-expanded.png', fullPage: true });
  
  // Check trait behavior preview is visible
  const behaviorPreview = await page.locator('text=Behavior Preview').count();
  console.log(`  Behavior Preview visible: ${behaviorPreview > 0 ? 'YES' : 'NO'}`);
  
  // Check spawn room dropdown
  const spawnSelect = page.locator('select');
  const selectCount = await spawnSelect.count();
  console.log(`  Spawn room dropdowns: ${selectCount}`);
  
  // Check "No rooms yet" message
  const noRooms = await page.locator('text=No rooms yet').count();
  console.log(`  "No rooms yet" hint visible: ${noRooms > 0 ? 'YES' : 'NO'}`);
  
  // Scroll to relationship matrix
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.waitForTimeout(200);
  await page.screenshot({ path: 'screenshots/agents-desktop-matrix.png', fullPage: true });
  
  // Check trust slider labels
  const hostileLabel = await page.locator('text=Hostile').count();
  const neutralLabel = await page.locator('text=Neutral').count();
  const alliedLabel = await page.locator('text=Allied').count();
  console.log(`  Trust labels (Hostile/Neutral/Allied): ${hostileLabel > 0}/${neutralLabel > 0}/${alliedLabel > 0}`);
  
  // Delete agent (desktop)
  console.log('  Testing desktop delete button...');
  const deleteBtns = page.locator('[aria-label="Delete agent"]');
  const dCount = await deleteBtns.count();
  console.log(`  Delete buttons: ${dCount}`);
  if (dCount > 0) {
    // Delete one visible on desktop
    const visibleDelete = page.locator('.hidden.md\:flex [aria-label="Delete agent"]');
    // Just check that the button is there, don't actually click to keep state
  }
  
  await page.close();
}

// Console error check
console.log('\n=== Console error check ===');
{
  const page = await browser.newPage({ viewport: { width: 375, height: 812 } });
  const errors = [];
  page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
  
  await page.goto('http://localhost:5179/creator', { waitUntil: 'networkidle', timeout: 15000 });
  await page.locator('button:has-text("Agents")').first().click();
  await page.waitForTimeout(500);
  await page.locator('button:has-text("Validate")').first().click();
  await page.waitForTimeout(500);
  
  console.log(`Console errors: ${errors.length}`);
  errors.forEach(e => console.log(`  - ${e}`));
  
  await page.close();
}

await browser.close();
console.log('\nAll tests completed.');
