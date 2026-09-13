import assert from "node:assert/strict";
import { chromium } from "playwright";
const base = process.env.E2E_WEB_BASE_URL || "http://127.0.0.1:3001";
const browser = await chromium.launch({ headless: true,
  ...(process.env.PLAYWRIGHT_CHROME_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROME_PATH } : {}) });
try {
  const context = await browser.newContext({ permissions: ["clipboard-read", "clipboard-write"] });
  const page = await context.newPage();
  await page.goto(`${base}/?example=sunglasses&mode=natural`);
  await page.locator("#example-select").waitFor();
  assert.equal(await page.locator("#example-select").inputValue(), "sunglasses");
  assert.equal(await page.getByRole("tab", { name: "Natural language", exact: true }).getAttribute("aria-selected"), "true");
  assert.equal(await page.locator(".stage").count(), 0);
  await page.getByRole("button", { name: "Copy example link", exact: true }).click();
  await page.getByText("Example link copied.", { exact: true }).waitFor();
  assert.equal(await page.evaluate(() => navigator.clipboard.readText()), page.url());
  await page.locator("#example-select").selectOption("running-shoes");
  await page.waitForURL("**example=running-shoes&mode=natural");
  await page.getByRole("tab", { name: "Structured query", exact: true }).click();
  await page.waitForURL("**example=running-shoes&mode=structured");
  await page.reload();
  await page.locator("#example-select").waitFor();
  assert.equal(await page.locator("#example-select").inputValue(), "running-shoes");
  await page.goto(`${base}/?example=missing&mode=invalid`);
  await page.locator("#example-select").waitFor();
  await page.waitForURL("**example=graphic-t-shirts&mode=structured");
  console.log("Sharing passed: deep links, clipboard, selection changes, reload, and invalid URL defaults.");
} finally { await browser.close(); }
