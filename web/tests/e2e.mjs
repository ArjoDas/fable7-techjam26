import assert from "node:assert/strict";
import { readFileSync, mkdirSync } from "node:fs";
import { chromium } from "playwright";

const webBase = process.env.E2E_WEB_BASE_URL || "http://127.0.0.1:3001";
const manifest = JSON.parse(readFileSync(new URL("../public/recordings/manifest.json", import.meta.url)));
const browser = await chromium.launch({ headless: true,
  ...(process.env.PLAYWRIGHT_CHROME_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROME_PATH } : {}) });
const errors = [];
const forbidden = [];
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: "reduce" });
  await context.route("**/*", route => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() !== "GET" || /\/readyz|\/v1\//.test(url.pathname)) forbidden.push(request.url());
    // The exported demo must work with every external service unavailable.
    return url.origin === new URL(webBase).origin ? route.continue() : route.abort();
  });
  const page = await context.newPage();
  page.on("pageerror", error => errors.push(error.message));
  await page.goto(webBase);
  await page.locator("#example-select").waitFor();
  assert.equal(await page.locator("#example-select option").count(), manifest.examples.length);
  await page.getByText("Static demo · Recorded engine responses", { exact: true }).waitFor();
  assert.equal(await page.getByRole("link", { name: "GitHub", exact: true }).getAttribute("href"), "https://github.com/ArjoDas/fable7-techjam26");
  assert.ok((await page.getByRole("link", { name: "Run the live demo locally ↗" }).getAttribute("href")).includes("/blob/main/README.md#fable7-web-demo-quickstart"));
  assert.equal(await page.locator('input[type="text"]').count(), 0);

  for (const example of manifest.examples) {
    for (const mode of ["structured", "natural"]) {
      await page.getByRole("tab", { name: mode === "natural" ? "Natural language" : "Structured query", exact: true }).click();
      await page.locator("#example-select").selectOption(example.id);
      if (await page.getByRole("button", { name: "Reset example", exact: true }).count()) {
        await page.getByRole("button", { name: "Reset example", exact: true }).click();
      }
      const recording = JSON.parse(readFileSync(new URL(`../public/recordings/${example.recordings[mode].file}`, import.meta.url)));
      await page.getByRole("button", { name: "Play example", exact: true }).click();
      for (const [index, turn] of recording.turns.entries()) {
        if (index) await page.getByRole("button", { name: /^Next turn/ }).click();
        await page.getByText(`Recorded shopper message · turn ${index + 1}`, { exact: true }).waitFor();
        await page.locator(".stage.revealed .product-card").first().waitFor();
        assert.equal(await page.locator(".recorded-message p").textContent(), turn.input);
        assert.deepEqual(await page.locator(".product-card .card-title").allTextContents(), turn.response.recommendations.map(p => p.title));
        assert.equal(await page.locator(".stage").count(), mode === "natural" ? 7 : 6);
      }
      assert.equal(await page.locator(".product-card").first().locator(".card-target-tag").count(), 1);
      assert.equal(await page.getByRole("button", { name: /^Next turn/ }).count(), 0);
      await page.locator(".turn-tab").first().click();
      await page.getByText("Recorded shopper message · turn 1", { exact: true }).waitFor();
      await page.getByRole("button", { name: "Replay animation" }).click();
      assert.equal(await page.locator(".turn-tab.active").textContent(), "1");
      console.log(example.id, mode, "all turns and replay passed");
    }
  }

  // Preserve the selected example when switching modes.
  await page.getByRole("tab", { name: "Structured query", exact: true }).click();
  assert.equal(await page.locator("#example-select").inputValue(), manifest.examples.at(-1).id);
  await page.getByRole("button", { name: "Play example", exact: true }).click();
  await page.locator(".stage.revealed .product-card").first().waitFor();
  for (const width of [1440, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 900 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `Overflow at ${width}`);
  }
  await page.setViewportSize({ width: 390, height: 900 });
  await page.getByRole("tab", { name: "Natural language", exact: true }).click();
  await page.getByRole("button", { name: "Play example", exact: true }).click();
  await page.getByRole("heading", { name: "Natural-language mapping", exact: true }).waitFor();
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  if (process.env.E2E_SHOT_DIR) {
    mkdirSync(process.env.E2E_SHOT_DIR, { recursive: true });
    await page.screenshot({ path: `${process.env.E2E_SHOT_DIR}/static-mobile.png`, fullPage: true });
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.screenshot({ path: `${process.env.E2E_SHOT_DIR}/static-desktop.png`, fullPage: true });
  }

  // A failed static download must be recoverable without starting an API.
  const retryPage = await context.newPage();
  let failManifest = true;
  await retryPage.route("**/recordings/manifest.json", route => failManifest ? route.fulfill({ status: 503, body: "unavailable" }) : route.continue());
  await retryPage.goto(webBase);
  await retryPage.getByText("Recordings could not be loaded", { exact: true }).waitFor();
  failManifest = false;
  await retryPage.getByRole("button", { name: "Try again", exact: true }).click();
  await retryPage.locator("#example-select").waitFor();
  let failRecording = true;
  await retryPage.route("**/recordings/*.structured.json", route => failRecording ? route.fulfill({ status: 404, body: "missing" }) : route.continue());
  await retryPage.getByRole("button", { name: "Play example", exact: true }).click();
  await retryPage.getByRole("alert").waitFor();
  failRecording = false;
  await retryPage.getByRole("button", { name: "Play example", exact: true }).click();
  await retryPage.locator(".stage.revealed").last().waitFor();
  assert.deepEqual(forbidden, [], "Static playback must not call any API or POST endpoint");
  assert.deepEqual(errors, []);
  console.log("Static demo passed: all sessions, mode switching, replay, mobile layouts, and error recovery; external services blocked.");
} finally { await browser.close(); }
