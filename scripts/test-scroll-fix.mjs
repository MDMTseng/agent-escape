import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
const page = await context.newPage();

await page.goto('http://localhost:5173/monitor', { waitUntil: 'networkidle' });
await page.waitForSelector('h1');

// Inject 25 narrative cards via dynamic import of the Zustand store
const injected = await page.evaluate(async () => {
  try {
    const mod = await import('/src/stores/gameStore.ts');
    if (!mod || !mod.useGameStore) return { error: 'no store export' };
    const cards = [];
    for (let i = 1; i <= 25; i++) {
      cards.push({
        tick: i,
        timestamp: Date.now() - (25 - i) * 10000,
        text: 'In the dimly lit chamber, shadows dance across ancient stone walls. Agent Alpha examines the peculiar inscription carved into the doorframe while Agent Beta rummages through a dusty cabinet. Tick ' + i + ' unfolds with mysterious revelations and unexpected discoveries that push the story forward into uncharted territory.',
        events: [
          { type: i % 3 === 0 ? 'move' : i % 3 === 1 ? 'talk' : 'examine', description: 'Event at tick ' + i + ': Agent performs action.', agent: 'Alpha', room: 'Chamber' }
        ]
      });
    }
    mod.useGameStore.setState({ narrativeEvents: cards, tick: 25 });
    return { ok: true, cardCount: cards.length };
  } catch(e) {
    return { error: e.message };
  }
});
console.log('Injection:', JSON.stringify(injected));
await page.waitForTimeout(1500);

// 1. Body must NOT scroll
const bodyCheck = await page.evaluate(() => {
  const b = document.body;
  return { scrollHeight: b.scrollHeight, clientHeight: b.clientHeight, scrolls: b.scrollHeight > b.clientHeight + 5 };
});
console.log('BODY:', JSON.stringify(bodyCheck));

// 2. Card count
const cardCount = await page.evaluate(() => document.querySelectorAll('article').length);
console.log('CARDS:', cardCount);

// 3. Find scrollable feed container
const feedInfo = await page.evaluate(() => {
  const all = [...document.querySelectorAll('*')].filter(el => {
    const s = getComputedStyle(el);
    return (s.overflowY === 'auto' || s.overflowY === 'scroll') && el.scrollHeight > el.clientHeight + 10;
  });
  return all.map(el => ({
    tag: el.tagName,
    cls: el.className.substring(0, 100),
    sh: el.scrollHeight,
    ch: el.clientHeight,
    st: el.scrollTop
  }));
});
console.log('SCROLLABLE:', JSON.stringify(feedInfo, null, 2));

// Screenshot with cards
await page.screenshot({ path: 'C:/Users/TRS001/Documents/workspace/agenttown/screenshots/review-P0-006-cards-desktop.png' });

// 4. Auto-scroll: should be near bottom
const autoCheck = await page.evaluate(() => {
  const c = [...document.querySelectorAll('*')].filter(el => {
    const s = getComputedStyle(el);
    return (s.overflowY === 'auto' || s.overflowY === 'scroll') && el.scrollHeight > el.clientHeight + 10 && el.tagName !== 'MAIN';
  })[0];
  if (!c) return { error: 'no feed container', checkMain: true };
  return { atBottom: c.scrollHeight - c.scrollTop - c.clientHeight < 100, scrollTop: Math.round(c.scrollTop), max: c.scrollHeight - c.clientHeight };
});
console.log('AUTO-SCROLL:', JSON.stringify(autoCheck));

// 5. Scroll up -> Jump to latest should appear
await page.evaluate(async () => {
  // Try feed container first, fall back to main
  const c = [...document.querySelectorAll('*')].filter(el => {
    const s = getComputedStyle(el);
    return (s.overflowY === 'auto' || s.overflowY === 'scroll') && el.scrollHeight > el.clientHeight + 10;
  });
  const target = c.find(el => el.tagName !== 'MAIN') || c[0];
  if (target) {
    target.scrollTop = 0;
    target.dispatchEvent(new Event('scroll'));
  }
});
await page.waitForTimeout(600);
const jumpVisible = await page.evaluate(() => !!document.querySelector('[aria-label="Jump to latest event"]'));
console.log('JUMP VISIBLE AFTER SCROLL UP:', jumpVisible);

await page.screenshot({ path: 'C:/Users/TRS001/Documents/workspace/agenttown/screenshots/review-P0-006-jump-btn.png' });

// 6. Click jump button
if (jumpVisible) {
  await page.click('[aria-label="Jump to latest event"]');
  await page.waitForTimeout(1200);
  const afterJump = await page.evaluate(() => {
    const c = [...document.querySelectorAll('*')].filter(el => {
      const s = getComputedStyle(el);
      return (s.overflowY === 'auto' || s.overflowY === 'scroll') && el.scrollHeight > el.clientHeight + 10;
    });
    const target = c.find(el => el.tagName !== 'MAIN') || c[0];
    if (!target) return { error: 'no container' };
    return { atBottom: target.scrollHeight - target.scrollTop - target.clientHeight < 100 };
  });
  console.log('AFTER JUMP:', JSON.stringify(afterJump));
}

// 7. Filter test
const filterResult = await page.evaluate(async () => {
  const btns = [...document.querySelectorAll('button')];
  const movBtn = btns.find(b => b.textContent.trim() === 'Movement');
  if (!movBtn) return { error: 'no Movement button' };
  movBtn.click();
  await new Promise(r => setTimeout(r, 400));
  const filtered = document.querySelectorAll('article').length;
  const allBtn = btns.find(b => b.textContent.trim() === 'All');
  if (allBtn) { allBtn.click(); await new Promise(r => setTimeout(r, 400)); }
  const all = document.querySelectorAll('article').length;
  return { filtered, all };
});
console.log('FILTER:', JSON.stringify(filterResult));

// 8. Mobile test
await page.setViewportSize({ width: 375, height: 812 });
await page.waitForTimeout(800);
const mobileCheck = await page.evaluate(() => ({
  bodyScrolls: document.body.scrollHeight > document.body.clientHeight + 5,
  cards: document.querySelectorAll('article').length,
}));
console.log('MOBILE:', JSON.stringify(mobileCheck));

await page.screenshot({ path: 'C:/Users/TRS001/Documents/workspace/agenttown/screenshots/review-P0-006-mobile-cards.png' });

await browser.close();
console.log('ALL TESTS COMPLETE');
