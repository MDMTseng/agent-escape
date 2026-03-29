import { chromium } from 'playwright';
import { mkdirSync } from 'fs';

const url = 'http://localhost:5179/creator';
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 375, height: 812 } });

try {
  mkdirSync('screenshots', { recursive: true });
  await page.goto(url, { waitUntil: 'networkidle', timeout: 15000 });
  
  // Go to Agents tab
  await page.locator('button:has-text("Agents")').first().click();
  await page.waitForTimeout(300);
  
  // Test 1: Click "The Detective" archetype
  console.log('Test 1: Add archetype agent...');
  await page.locator('button:has-text("The Detective")').click();
  await page.waitForTimeout(300);
  
  // Check if agent card appeared
  const agentCount = await page.locator('text=1 agent').count();
  console.log(`  Agent count text visible: ${agentCount > 0 ? 'YES' : 'NO'}`);
  
  // Test 2: Add another archetype
  console.log('Test 2: Add second archetype...');
  await page.locator('button:has-text("The Scholar")').click();
  await page.waitForTimeout(300);
  
  const agentCount2 = await page.locator('text=2 agents').count();
  console.log(`  2 agents text visible: ${agentCount2 > 0 ? 'YES' : 'NO'}`);
  
  // Screenshot with 2 agents
  await page.screenshot({ path: 'screenshots/agents-with-data-mobile.png', fullPage: true });
  console.log('  Screenshot: agents-with-data-mobile.png');
  
  // Test 3: Expand first agent card
  console.log('Test 3: Expand agent card...');
  const expandBtns = page.locator('[aria-label="Expand"], [aria-label="Collapse"]');
  const expandCount = await expandBtns.count();
  console.log(`  Expand buttons found: ${expandCount}`);
  if (expandCount > 0) {
    await expandBtns.first().click();
    await page.waitForTimeout(300);
    await page.screenshot({ path: 'screenshots/agents-expanded-mobile.png', fullPage: true });
    console.log('  Screenshot: agents-expanded-mobile.png');
  }
  
  // Test 4: Check relationship matrix appears
  console.log('Test 4: Relationship matrix...');
  const matrixVisible = await page.locator('text=Relationship Matrix').count();
  console.log(`  Relationship Matrix visible: ${matrixVisible > 0 ? 'YES' : 'NO'}`);
  
  // Test 5: Check trust slider exists
  const sliders = page.locator('input[type="range"]');
  const sliderCount = await sliders.count();
  console.log(`  Trust sliders found: ${sliderCount}`);
  
  // Scroll down to matrix
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.waitForTimeout(300);
  await page.screenshot({ path: 'screenshots/agents-matrix-mobile.png', fullPage: true });
  console.log('  Screenshot: agents-matrix-mobile.png');
  
  // Test 6: Add blank agent
  console.log('Test 6: Add blank agent via button...');
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(200);
  await page.locator('button:has-text("Add Agent")').first().click();
  await page.waitForTimeout(300);
  const agentCount3 = await page.locator('text=3 agents').count();
  console.log(`  3 agents text visible: ${agentCount3 > 0 ? 'YES' : 'NO'}`);
  
  // Test 7: Check trait behavior preview
  console.log('Test 7: Trait behavior preview...');
  const previewVisible = await page.locator('text=Behavior Preview').count();
  console.log(`  Behavior Preview visible: ${previewVisible > 0 ? 'YES' : 'NO'}`);
  
  // Test 8: Delete agent (desktop only - look for delete button)
  console.log('Test 8: Desktop delete...');
  const deleteBtns = page.locator('[aria-label="Delete agent"]');
  const deleteCount = await deleteBtns.count();
  console.log(`  Delete buttons found (mobile hides them): ${deleteCount}`);
  
  // Test 9: Now go to Validate tab and check validation
  console.log('Test 9: Validate tab...');
  await page.locator('button:has-text("Validate")').first().click();
  await page.waitForTimeout(300);
  await page.screenshot({ path: 'screenshots/validate-with-agents-mobile.png', fullPage: true });
  console.log('  Screenshot: validate-with-agents-mobile.png');
  
  // Check for Issues Found or Ready
  const issuesFound = await page.locator('text=Issues Found').count();
  const readyWarnings = await page.locator('text=Ready with Warnings').count();
  const readyToPlay = await page.locator('text=Ready to Play').count();
  console.log(`  Issues Found: ${issuesFound > 0}, Ready w/ Warnings: ${readyWarnings > 0}, Ready: ${readyToPlay > 0}`);
  
  // Check Save button exists
  const saveBtn = await page.locator('button:has-text("Save Scene")').count();
  const playBtn = await page.locator('button:has-text("Play Scene")').count();
  console.log(`  Save button: ${saveBtn > 0 ? 'YES' : 'NO'}, Play button: ${playBtn > 0 ? 'YES' : 'NO'}`);
  
  // Check Play button is disabled (should be with failures)
  const playDisabled = await page.locator('button:has-text("Play Scene")').isDisabled();
  console.log(`  Play button disabled (expected when fails exist): ${playDisabled}`);
  
  // Test 10: Console errors
  const errors = [];
  page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
  await page.waitForTimeout(500);
  console.log(`  Console errors: ${errors.length}`);
  
  console.log('\nAll tests completed.');
  
} catch (err) {
  console.error('FAILED:', err.message);
} finally {
  await page.close();
  await browser.close();
}
