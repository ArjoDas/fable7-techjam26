import { chromium } from "playwright";

const chromePath =
  process.env.PLAYWRIGHT_CHROME_PATH ||
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

const browser = await chromium.launch({
  executablePath: chromePath,
  headless: true,
});

const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [];
page.on("console", (message) => {
  if (message.type() === "error") {
    errors.push(`${message.text()} ${message.location().url || ""}`.trim());
  }
});
page.on("pageerror", (error) => errors.push(error.message));

try {
  await page.goto("http://127.0.0.1:3000", { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: /shopping search/i }).waitFor();
  await page.getByRole("link", { name: /explore internals/i }).waitFor();
  await page.screenshot({ path: "/private/tmp/techjam-landing.png", fullPage: true });

  await page.goto("http://127.0.0.1:3000/demo", { waitUntil: "networkidle" });
  await page.locator(".connection-dot.ready").waitFor({ timeout: 20_000 });
  await page.getByLabel("Describe what you need").fill(
    "Recommend a durable leather belt under $50",
  );
  await page.locator(".composer .send-button").click();
  await page.locator(".product-card").first().waitFor({ timeout: 20_000 });
  if ((await page.locator(".trace-panel").count()) !== 0) {
    throw new Error("Consumer demo exposed the trace panel");
  }

  await page.goto("http://127.0.0.1:3000/internals", { waitUntil: "networkidle" });
  await page.locator(".connection-dot.ready").waitFor({ timeout: 20_000 });
  await page.getByLabel("Choose the next message").selectOption({ index: 0 });
  await page.locator(".composer .send-button").click();
  await page.locator(".status-badge.compatible").waitFor({ timeout: 20_000 });
  await page.getByText("BM25", { exact: true }).waitFor();
  await page.locator(".product-card").first().waitFor();
  await page.locator("canvas").waitFor();
  await page.waitForTimeout(3_000);
  await page.getByText("product in view", { exact: true }).waitFor();
  await page.screenshot({ path: "/private/tmp/techjam-internals.png", fullPage: true });

  if (errors.length) {
    throw new Error(`Browser console errors:\n${errors.join("\n")}`);
  }
  process.stdout.write("Landing, free-form demo, and guided internals flows passed.\n");
} finally {
  await browser.close();
}
