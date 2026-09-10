import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import path from "node:path";

const webBase = "http://localhost:3000";
const apiBase = "http://localhost:8000";
const shotDir = path.join(process.cwd(), "..", "tmp", "shots-redesign");
mkdirSync(shotDir, { recursive: true });
const shot = (name) => path.join(shotDir, `${name}.png`);

for (let attempt = 0; attempt < 120; attempt += 1) {
  try {
    if ((await fetch(`${apiBase}/readyz`)).status === 200) break;
  } catch {}
  await new Promise((resolve) => setTimeout(resolve, 2000));
}

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });

await page.goto(webBase, { waitUntil: "networkidle" });
await page.locator("#example-select").waitFor({ timeout: 60_000 });
await page.screenshot({ path: shot("landing-structured") });

// Natural mode should default to free text input.
await page.getByRole("tab", { name: "Natural language" }).click();
await page.locator("#free-first").waitFor({ timeout: 5_000 });
await page.screenshot({ path: shot("landing-natural-free") });

// Structured buying run to turn 2 for the green target check.
await page.getByRole("tab", { name: "Structured query" }).click();
const options = await page
  .locator("#example-select option")
  .evaluateAll((nodes) => nodes.map((node) => node.value));
await page.locator("#example-select").selectOption(
  options.find((value) => value.startsWith("buying-")),
);
await page.getByRole("button", { name: "Run" }).click();
await page.locator(".stage-rail .stage").last().waitFor({ timeout: 30_000 });
await page.waitForTimeout(9_000);
await page.getByRole("button", { name: /Next turn/ }).click();
await page.locator(".stage-rail .stage").last().waitFor({ timeout: 30_000 });
await page.waitForTimeout(9_000);
await page.screenshot({ path: shot("structured-top10"), fullPage: true });

await browser.close();
process.stdout.write("visual check screenshots written\n");
