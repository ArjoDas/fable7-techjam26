import assert from "node:assert/strict";
import { chromium } from "playwright";

const webBase = process.env.E2E_WEB_BASE_URL || "http://127.0.0.1:3001";
const browser = await chromium.launch({
  headless: true,
  ...(process.env.PLAYWRIGHT_CHROME_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROME_PATH } : {}),
});
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: "reduce" });
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto(webBase);
  await page.locator("#example-select").waitFor({ timeout: 60000 });
  const responsePromise = page.waitForResponse(r => r.url().endsWith(".structured.json"));
  await page.getByRole("button", { name: "Play example", exact: true }).click();
  const payload = await (await responsePromise).json();
  const product = payload.turns[0].response.recommendations[0];
  const card = page.getByRole("button", { name: `Preview ${product.title}`, exact: true });
  await card.waitFor();
  let detailRequests = 0;
  page.on("request", request => { if (request.url().includes("/recordings/") || request.method() !== "GET") detailRequests++; });
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await card.focus();
    await page.keyboard.press("Enter");
    const dialog = page.getByRole("dialog");
    await dialog.waitFor();
    assert.equal(await dialog.getByRole("heading", { level: 2 }).textContent(), product.title);
    for (const text of [...product.features, ...product.description]) {
      assert.ok((await dialog.textContent()).includes(text));
    }
    assert.equal(await page.evaluate(() => document.body.style.overflow), "hidden");
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    assert.equal(await dialog.evaluate(el => el.scrollWidth > el.clientWidth), false);
    // The native modal must retain keyboard focus in both directions.
    await page.keyboard.press("Shift+Tab");
    assert.equal(await dialog.evaluate(el => el.contains(document.activeElement)), true);
    await page.keyboard.press("Tab");
    assert.equal(await dialog.evaluate(el => el.contains(document.activeElement)), true);
    await page.keyboard.press("Escape");
    await dialog.waitFor({ state: "detached" });
    assert.equal(await card.evaluate(el => el === document.activeElement), true);
    await card.click();
    await page.getByRole("button", { name: "Close preview" }).click();
    await dialog.waitFor({ state: "detached" });
    assert.equal(await card.evaluate(el => el === document.activeElement), true);
  }
  assert.equal(detailRequests, 0, "Opening details must not fetch another catalog payload");
  assert.deepEqual(errors, []);
  console.log("Product preview passed: complete content, desktop/mobile, keyboard, focus restoration, no extra API requests.");
} finally { await browser.close(); }
