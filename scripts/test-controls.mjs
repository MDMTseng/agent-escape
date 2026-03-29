import { chromium } from 'playwright';

const browser = await chromium.launch();
const page = await browser.newPage();
await page.setViewportSize({ width: 1280, height: 800 });

// Navigate to monitor
await page.goto('http://localhost:5173/monitor', { waitUntil: 'networkidle' });
await page.waitForTimeout(2000);

// Find the play/pause button
const playBtn = page.locator('button[aria-label="Play simulation"]');
const pauseBtn = page.locator('button[aria-label="Pause simulation"]');
const stepBtn = page.locator('button[aria-label="Step one tick"]');

// 1) Initial state: should show Play button, Step should be enabled
console.log('--- Initial State ---');
const playVisible = await playBtn.isVisible().catch(() => false);
const pauseVisible = await pauseBtn.isVisible().catch(() => false);
console.log(`Play button visible: ${playVisible}`);
console.log(`Pause button visible: ${pauseVisible}`);

const stepDisabled = await stepBtn.isDisabled();
console.log(`Step button disabled: ${stepDisabled}`);

// Take screenshot of initial state
await page.screenshot({ path: 'screenshots/review-P0-009-initial.png' });

// 2) Click Play
console.log('\n--- After clicking Play ---');
if (playVisible) {
  await playBtn.click();
  await page.waitForTimeout(1500);
  
  const playVisibleAfter = await playBtn.isVisible().catch(() => false);
  const pauseVisibleAfter = await pauseBtn.isVisible().catch(() => false);
  console.log(`Play button visible: ${playVisibleAfter}`);
  console.log(`Pause button visible: ${pauseVisibleAfter}`);
  
  const stepDisabledAfter = await stepBtn.isDisabled();
  console.log(`Step button disabled: ${stepDisabledAfter}`);
  
  await page.screenshot({ path: 'screenshots/review-P0-009-playing.png' });
  
  // 3) Click Pause
  console.log('\n--- After clicking Pause ---');
  if (pauseVisibleAfter) {
    await pauseBtn.click();
    await page.waitForTimeout(1500);
    
    const playVisibleFinal = await playBtn.isVisible().catch(() => false);
    const pauseVisibleFinal = await pauseBtn.isVisible().catch(() => false);
    console.log(`Play button visible: ${playVisibleFinal}`);
    console.log(`Pause button visible: ${pauseVisibleFinal}`);
    
    const stepDisabledFinal = await stepBtn.isDisabled();
    console.log(`Step button disabled: ${stepDisabledFinal}`);
    
    await page.screenshot({ path: 'screenshots/review-P0-009-paused.png' });
  } else {
    console.log('FAIL: Pause button not visible after clicking Play!');
  }
} else {
  console.log('FAIL: Play button not visible initially!');
}

// 4) Test Step button
console.log('\n--- Step Test ---');
const playVisibleForStep = await playBtn.isVisible().catch(() => false);
if (playVisibleForStep) {
  // Get current tick
  const tickBefore = await page.locator('.text-gold.font-mono').textContent().catch(() => 'N/A');
  console.log(`Tick before step: ${tickBefore}`);
  
  const stepDisabledForStep = await stepBtn.isDisabled();
  console.log(`Step disabled before step: ${stepDisabledForStep}`);
  
  if (!stepDisabledForStep) {
    await stepBtn.click();
    await page.waitForTimeout(5000); // Step takes time (API call + agent processing)
    
    const tickAfter = await page.locator('.text-gold.font-mono').textContent().catch(() => 'N/A');
    console.log(`Tick after step: ${tickAfter}`);
    
    await page.screenshot({ path: 'screenshots/review-P0-009-stepped.png' });
  } else {
    console.log('FAIL: Step button is disabled when paused');
  }
}

// 5) Test Quit while playing
console.log('\n--- Quit Test ---');
// First resume
await playBtn.click().catch(() => {});
await page.waitForTimeout(1000);
const quitBtn = page.locator('button[aria-label="Quit to library"]');
const quitVisible = await quitBtn.isVisible();
console.log(`Quit button visible: ${quitVisible}`);

if (quitVisible) {
  await quitBtn.click();
  await page.waitForTimeout(2000);
  const currentUrl = page.url();
  console.log(`URL after quit: ${currentUrl}`);
  console.log(`Navigated to library: ${currentUrl.includes('/library')}`);
  await page.screenshot({ path: 'screenshots/review-P0-009-quit.png' });
}

console.log('\n--- Test Complete ---');
await browser.close();
