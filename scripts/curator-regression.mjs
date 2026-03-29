import { chromium } from 'playwright';
const browser = await chromium.launch();
const errors = [];

const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
page.on('console', msg => {
  if (msg.type() === 'error') errors.push(msg.text());
});

// Check home
await page.goto('http://localhost:5173/', { waitUntil: 'networkidle', timeout: 15000 });
await page.waitForTimeout(1000);
console.log('Home loaded');

// Check library
await page.goto('http://localhost:5173/library', { waitUntil: 'networkidle', timeout: 15000 });
await page.waitForTimeout(1000);
console.log('Library loaded');

// Check create
await page.goto('http://localhost:5173/create', { waitUntil: 'networkidle', timeout: 15000 });
await page.waitForTimeout(1000);
console.log('Create loaded');

// Check monitor with all features
await page.goto('http://localhost:5173/monitor', { waitUntil: 'networkidle', timeout: 15000 });
await page.waitForTimeout(2000);

// Verify agent strip
const agentCards = page.locator('[class*="border-gold"], [class*="text-gold"]').first();
console.log('Agent cards present:', await agentCards.count() > 0);

// Verify escape chain
const escapeChain = page.locator('text=0 /');
console.log('Escape chain present:', await escapeChain.count() > 0);

// Verify puzzle progress
const puzzleProgress = page.locator('text=Puzzle Progress');
console.log('Puzzle progress present:', await puzzleProgress.count() > 0);

// Verify sim controls
const playBtn = page.locator('button[aria-label="Play"], button[aria-label="Resume simulation"]');
const stepBtn = page.locator('button[aria-label="Step one tick"]');
console.log('Play/pause button:', await playBtn.count() > 0);
console.log('Step button:', await stepBtn.count() > 0);

// Verify save/load
const saveBtn = page.locator('button[aria-label="Save game"]');
const loadBtn = page.locator('button[aria-label="Load game"]');
console.log('Save button:', await saveBtn.count() > 0);
console.log('Load button:', await loadBtn.count() > 0);

// Verify thought bubbles toggle
const thoughtsLabel = page.locator('text=Thoughts:');
console.log('Thoughts label:', await thoughtsLabel.count() > 0);

// Verify interactive map toggle
const mapToggle = page.locator('text=Room Map');
console.log('Room Map toggle:', await mapToggle.count() > 0);

// Check for console errors
if (errors.length > 0) {
  console.log('\nConsole errors:');
  errors.forEach(e => console.log('  ERROR:', e));
} else {
  console.log('\nNo console errors');
}

await page.close();
await browser.close();
