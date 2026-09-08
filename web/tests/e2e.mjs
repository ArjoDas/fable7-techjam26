import { chromium } from "playwright";

const chromePath =
  process.env.PLAYWRIGHT_CHROME_PATH ||
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const webBase = (process.env.E2E_WEB_BASE_URL || "http://localhost:3000").replace(/\/$/, "");
const apiOverride = process.env.E2E_API_BASE_URL?.replace(/\/$/, "");

const browser = await chromium.launch({
  executablePath: chromePath,
  headless: true,
});

const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [];
let sessionCreates = 0;
page.on("request", (request) => {
  if (request.method() === "POST" && request.url().endsWith("/v1/sessions")) {
    sessionCreates += 1;
  }
});
page.on("console", (message) => {
  if (message.type() === "error") {
    errors.push(`${message.text()} ${message.location().url || ""}`.trim());
  }
});
page.on("pageerror", (error) => errors.push(error.message));
if (apiOverride) {
  await page.route("http://localhost:8000/**", async (route) => {
    const original = new URL(route.request().url());
    await route.continue({ url: `${apiOverride}${original.pathname}${original.search}` });
  });
}

try {
  await page.goto(webBase, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: /shopping search/i }).waitFor();
  await page.getByRole("link", { name: /Fable7/i }).waitFor();
  await page.getByRole("link", { name: /explore internals/i }).waitFor();
  await page.screenshot({ path: "/private/tmp/techjam-landing.png", fullPage: true });

  await page.goto(`${webBase}/demo`, { waitUntil: "networkidle" });
  await page.locator(".connection-dot.ready").waitFor({ timeout: 20_000 });
  await page.getByLabel("Describe what you need").fill(
    "Recommend a durable leather belt under $50",
  );
  await page.locator(".composer .send-button").click();
  await page.locator(".product-card").first().waitFor({ timeout: 20_000 });
  if ((await page.locator(".trace-panel").count()) !== 0) {
    throw new Error("Consumer demo exposed the trace panel");
  }

  await page.goto(`${webBase}/internals`, { waitUntil: "networkidle" });
  await page.locator(".connection-dot.ready").waitFor({ timeout: 20_000 });
  if ((await page.locator(".app-header").getByRole("button", { name: "New session" }).count()) !== 0) {
    throw new Error("Session controls are still rendered in the navbar");
  }
  await page.locator(".chat-column").getByRole("button", { name: "New session" }).waitFor();
  await page.getByRole("button", { name: /^Buy/ }).click();
  await page.getByLabel("Choose the next message").selectOption({ index: 0 });
  const buyingPreview = await page.locator(".option-preview").textContent();
  if (!buyingPreview || buyingPreview.includes("still exploring")) {
    throw new Error("Buy intent did not expose a buying opening");
  }
  await page.locator(".composer .send-button").click();
  await page.locator(".status-badge.compatible").waitFor({ timeout: 20_000 });
  await page.getByRole("heading", { name: "specific buying" }).waitFor();
  await page.getByText("BM25", { exact: true }).waitFor();
  await page.locator(".product-card").first().waitFor();
  await page.locator("canvas").waitFor();
  await page.waitForTimeout(3_000);
  await page.getByText(/products? in view/i).waitFor();

  const sessionsBeforeIntentSwitch = sessionCreates;
  await page.getByRole("button", { name: /^Browse/ }).click();
  await page.locator(".turn-count").filter({ hasText: "Turn 2" }).waitFor();
  await page.getByRole("heading", { name: "exploratory browsing" }).waitFor({ timeout: 20_000 });
  await page.getByText("I'm changing my shopping intent to browsing.", { exact: true }).waitFor();
  if (sessionCreates !== sessionsBeforeIntentSwitch) {
    throw new Error("Changing intent created a new backend session");
  }
  await page.locator(".product-card").first().waitFor();

  const layout = await page.evaluate(() => ({
    viewportHeight: window.innerHeight,
    pageHeight: document.documentElement.scrollHeight,
    recommendationsOverflow: getComputedStyle(document.querySelector(".recommendations-region")).overflowY,
    messageFont: parseFloat(getComputedStyle(document.querySelector(".message p")).fontSize),
    fieldNoteFont: parseFloat(getComputedStyle(document.querySelector(".field-note")).fontSize),
    ribbonFont: parseFloat(getComputedStyle(document.querySelector(".catalog-ribbon")).fontSize),
  }));
  if (layout.pageHeight > layout.viewportHeight + 1 || layout.recommendationsOverflow !== "auto") {
    throw new Error(`Desktop panels are not isolated: ${JSON.stringify(layout)}`);
  }
  if (layout.messageFont < 15 || layout.fieldNoteFont < 12 || layout.ribbonFont < 11) {
    throw new Error(`Key interface copy is still too small: ${JSON.stringify(layout)}`);
  }
  await page.screenshot({ path: "/private/tmp/techjam-internals.png", fullPage: true });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${webBase}/internals`, { waitUntil: "networkidle" });
  await page.locator(".connection-dot.ready").waitFor({ timeout: 20_000 });
  const mobileWidth = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
  }));
  if (mobileWidth.content > mobileWidth.viewport + 1) {
    throw new Error(`Mobile layout overflows horizontally: ${JSON.stringify(mobileWidth)}`);
  }

  if (errors.length) {
    throw new Error(`Browser console errors:\n${errors.join("\n")}`);
  }
  process.stdout.write("Landing, free-form, intent switching, overflow, typography, and mobile flows passed.\n");
} finally {
  await browser.close();
}
