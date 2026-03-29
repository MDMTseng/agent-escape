import { chromium } from 'playwright';
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
await page.goto('http://localhost:5173/library', { waitUntil: 'networkidle' });
await page.waitForTimeout(1500);

// Check that main is scrollable (cards should be in main's overflow-y-auto)
const mainScroll = await page.evaluate(() => {
  const main = document.querySelector('main');
  if (!main) return { error: 'no main' };
  return {
    overflowY: getComputedStyle(main).overflowY,
    scrollHeight: main.scrollHeight,
    clientHeight: main.clientHeight,
    canScroll: main.scrollHeight > main.clientHeight + 5
  };
});
console.log('LIBRARY MAIN:', JSON.stringify(mainScroll));

// Check console for errors
await browser.close();
console.log('LIBRARY CHECK COMPLETE');
