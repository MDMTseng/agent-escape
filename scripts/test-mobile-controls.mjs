import { chromium } from 'playwright';

const browser = await chromium.launch();
const page = await browser.newPage();
await page.setViewportSize({ width: 375, height: 812 });

// Load story
await fetch('http://localhost:8741/api/stories/9/play', { method: 'POST' });
await page.goto('http://localhost:5173/monitor', { waitUntil: 'networkidle' });
await page.waitForTimeout(3000);

await page.screenshot({ path: 'screenshots/P0-009-mobile-initial.png' });

// Measure touch targets
const playBtn = page.locator('button[aria-label="Play simulation"]');
const stepBtn = page.locator('button[aria-label="Step one tick"]');
const quitBtn = page.locator('button[aria-label="Quit to library"]');

const playBox = await playBtn.boundingBox();
const stepBox = await stepBtn.boundingBox();
const quitBox = await quitBtn.boundingBox();

console.log('Touch target sizes:');
console.log(`  Play: ${playBox?.width}x${playBox?.height} at y=${playBox?.y}`);
console.log(`  Step: ${stepBox?.width}x${stepBox?.height} at y=${stepBox?.y}`);
console.log(`  Quit: ${quitBox?.width}x${quitBox?.height} at y=${quitBox?.y}`);

// Check if controls are in thumb zone (bottom third = below y=541)
const thumbZoneY = 812 * 0.67;
console.log(`\nThumb zone starts at y=${thumbZoneY}`);
console.log(`  Play in thumb zone: ${playBox?.y > thumbZoneY}`);
console.log(`  Step in thumb zone: ${stepBox?.y > thumbZoneY}`);
console.log(`  Quit in thumb zone: ${quitBox?.y > thumbZoneY}`);

// Check viewport height - controls bar should be above the bottom nav
const viewportHeight = 812;
console.log(`\nControl bar y-positions (viewport: ${viewportHeight}px):`);
console.log(`  Play bottom edge: ${playBox?.y + playBox?.height}`);
console.log(`  Controls are visible (not under nav): ${(playBox?.y + playBox?.height) < viewportHeight}`);

await browser.close();
