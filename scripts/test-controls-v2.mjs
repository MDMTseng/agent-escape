import { chromium } from 'playwright';

const browser = await chromium.launch();
const page = await browser.newPage();
await page.setViewportSize({ width: 1280, height: 800 });

// Load story first 
console.log('Loading story...');
const loadRes = await fetch('http://localhost:8741/api/stories/9/play', { method: 'POST' });
console.log(`Load status: ${loadRes.status}`);

await page.goto('http://localhost:5173/monitor', { waitUntil: 'networkidle' });
await page.waitForTimeout(3000);

const getButtonState = async () => {
  const playVisible = await page.locator('button[aria-label="Play simulation"]').isVisible().catch(() => false);
  const pauseVisible = await page.locator('button[aria-label="Pause simulation"]').isVisible().catch(() => false);
  const stepDisabled = await page.locator('button[aria-label="Step one tick"]').isDisabled().catch(() => 'N/A');
  
  // Check for spinner in play/pause button
  const spinnerInBtn = await page.locator('button[aria-label="Play simulation"] .animate-spin, button[aria-label="Pause simulation"] .animate-spin').isVisible().catch(() => false);
  
  return { playVisible, pauseVisible, stepDisabled, spinnerInBtn };
};

// 1. Initial state
console.log('\n=== INITIAL STATE ===');
let state = await getButtonState();
console.log(JSON.stringify(state, null, 2));
await page.screenshot({ path: 'screenshots/P0-009-v2-initial.png' });

// 2. Click Play
console.log('\n=== CLICK PLAY ===');
await page.locator('button[aria-label="Play simulation"]').click();
await page.waitForTimeout(500);
state = await getButtonState();
console.log('After 500ms:', JSON.stringify(state, null, 2));

// Wait for the tick to complete (API call + LLM processing can take 10-30s)
console.log('Waiting for tick to complete...');
await page.waitForTimeout(15000);
state = await getButtonState();
console.log('After 15s:', JSON.stringify(state, null, 2));
await page.screenshot({ path: 'screenshots/P0-009-v2-playing.png' });

// 3. Click Pause
console.log('\n=== CLICK PAUSE ===');
const pauseBtn = page.locator('button[aria-label="Pause simulation"]');
if (await pauseBtn.isVisible().catch(() => false)) {
  await pauseBtn.click();
  await page.waitForTimeout(500);
  state = await getButtonState();
  console.log('After 500ms:', JSON.stringify(state, null, 2));
  
  // Wait longer for pause to take effect
  await page.waitForTimeout(10000);
  state = await getButtonState();
  console.log('After 10s:', JSON.stringify(state, null, 2));
  await page.screenshot({ path: 'screenshots/P0-009-v2-paused.png' });
} else {
  console.log('Pause button NOT visible. Checking what we have...');
  const playBtn = page.locator('button[aria-label="Play simulation"]');
  const playVis = await playBtn.isVisible().catch(() => false);
  console.log(`Play visible instead: ${playVis}`);
  await page.screenshot({ path: 'screenshots/P0-009-v2-paused-missing.png' });
}

// 4. Step test
console.log('\n=== STEP TEST ===');
state = await getButtonState();
console.log('Before step:', JSON.stringify(state, null, 2));

const tickEl = page.locator('.text-gold.font-mono').first();
const tickBefore = await tickEl.textContent().catch(() => '?');
console.log(`Tick before: ${tickBefore}`);

if (!state.stepDisabled && state.playVisible) {
  await page.locator('button[aria-label="Step one tick"]').click();
  console.log('Step clicked, waiting for tick processing...');
  await page.waitForTimeout(20000);
  const tickAfter = await tickEl.textContent().catch(() => '?');
  console.log(`Tick after: ${tickAfter}`);
  const incremented = parseInt(tickAfter) > parseInt(tickBefore);
  console.log(`Tick incremented: ${incremented}`);
  await page.screenshot({ path: 'screenshots/P0-009-v2-stepped.png' });
} else {
  console.log('Step is disabled or not in paused state, skipping step test');
}

// 5. Quit test
console.log('\n=== QUIT TEST ===');
const quitBtn = page.locator('button[aria-label="Quit to library"]');
await quitBtn.click();
await page.waitForTimeout(3000);
console.log(`Final URL: ${page.url()}`);
console.log(`At library: ${page.url().includes('/library')}`);
await page.screenshot({ path: 'screenshots/P0-009-v2-quit.png' });

await browser.close();
console.log('\n=== DONE ===');
