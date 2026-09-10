import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import path from "node:path";

const webBase = (process.env.E2E_WEB_BASE_URL || "http://localhost:3000").replace(
  /\/$/,
  "",
);
const apiBase = (process.env.E2E_API_BASE_URL || "http://localhost:8000").replace(
  /\/$/,
  "",
);
const shotDir = process.env.E2E_SHOT_DIR || path.join(process.cwd(), "..", "tmp", "shots");
mkdirSync(shotDir, { recursive: true });
const shot = (name) => path.join(shotDir, `${name}.png`);

// Wait for the API to finish indexing before opening the page.
for (let attempt = 0; attempt < 120; attempt += 1) {
  try {
    const ready = await fetch(`${apiBase}/readyz`);
    if (ready.status === 200) break;
  } catch {
    /* server still starting */
  }
  await new Promise((resolve) => setTimeout(resolve, 2000));
}

const launchOptions = { headless: true };
if (process.env.PLAYWRIGHT_CHROME_PATH) {
  launchOptions.executablePath = process.env.PLAYWRIGHT_CHROME_PATH;
}
const browser = await chromium.launch(launchOptions);
const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
const errors = [];
page.on("console", (message) => {
  if (message.type() === "error") {
    errors.push(`${message.text()} ${message.location().url || ""}`.trim());
  }
});
page.on("pageerror", (error) => errors.push(error.message));

const surfaced = [];

async function waitForStages() {
  await page.locator(".stage-rail .stage").last().waitFor({ timeout: 30_000 });
  // Let the staged reveal timeline and FLIP animations finish.
  await page.waitForTimeout(9_000);
}

async function decisionWord() {
  return (await page.locator(".decision-word").textContent())?.trim();
}

try {
  await page.goto(webBase, { waitUntil: "networkidle" });
  await page.getByRole("heading", { name: /From prompt to results/i }).waitFor();
  await page
    .locator("#example-select")
    .waitFor({ timeout: 60_000 });
  await page.screenshot({ path: shot("01-landing"), fullPage: false });

  // ── Structured buying example: abstain on turn 1, top 10 on turn 2 ──
  const options = await page
    .locator("#example-select option")
    .evaluateAll((nodes) => nodes.map((node) => ({ value: node.value, label: node.textContent })));
  const buying = options.find((option) => option.value.startsWith("buying-"));
  const rotation = options.find((option) => option.value.startsWith("rotation-"));
  if (!buying || !rotation) {
    throw new Error(`Missing curated examples: ${JSON.stringify(options)}`);
  }

  await page.locator("#example-select").selectOption(buying.value);
  await page.getByRole("button", { name: "Run" }).click();
  await waitForStages();
  const turn1Decision = await decisionWord();
  if (!/abstain/i.test(turn1Decision || "")) {
    throw new Error(`Expected turn 1 abstention, saw: ${turn1Decision}`);
  }
  const turn1Cards = await page.locator(".product-card").count();
  if (turn1Cards !== 1) {
    throw new Error(`Abstention should show exactly 1 card, saw ${turn1Cards}`);
  }
  surfaced.push(
    `single-element abstention: "${buying.label?.trim()}" turn 1 → decision "${turn1Decision}", 1 product card`,
  );
  await page.screenshot({ path: shot("02-structured-abstain"), fullPage: true });

  await page.getByRole("button", { name: /Next turn/ }).click();
  await waitForStages();
  const turn2Decision = await decisionWord();
  if (!/top 10/i.test(turn2Decision || "")) {
    throw new Error(`Expected turn 2 top 10, saw: ${turn2Decision}`);
  }
  const turn2Cards = await page.locator(".product-card").count();
  if (turn2Cards < 2) {
    throw new Error(`Top-10 release should show many cards, saw ${turn2Cards}`);
  }
  const foundNote = await page
    .getByText(/reached rank 1 in \d+ turns?/i)
    .textContent();
  const targetCard = page.locator(".product-card.is-target");
  if ((await targetCard.count()) !== 1) {
    throw new Error("Target card is not highlighted in the top-10 grid");
  }
  surfaced.push(
    `top 10: "${buying.label?.trim()}" turn 2 → decision "${turn2Decision}", ${turn2Cards} cards, target highlighted (${foundNote?.trim()})`,
  );
  await page.screenshot({ path: shot("03-structured-top10"), fullPage: true });

  // ── Rotation example: repeat the same clue on turn 3 ──
  await page.getByRole("button", { name: "New run" }).click();
  await page.locator("#example-select").selectOption(rotation.value);
  await page.getByRole("button", { name: "Run" }).click();
  await waitForStages();
  for (let step = 0; step < 2; step += 1) {
    await page.getByRole("button", { name: /Next turn/ }).click();
    await waitForStages();
  }
  const rotationDecision = await decisionWord();
  if (!/rotate/i.test(rotationDecision || "")) {
    throw new Error(`Expected rotation on turn 3, saw: ${rotationDecision}`);
  }
  await page.locator(".skipped-chip").first().waitFor();
  surfaced.push(
    `rotation: "${rotation.label?.trim()}" turn 3 (same clue repeated) → decision "${rotationDecision}", previously shown items skipped`,
  );
  await page.screenshot({ path: shot("04-rotation"), fullPage: true });

  // ── Natural language: free typing through the semantic stage ──
  await page.getByRole("button", { name: "New run" }).click();
  await page.getByRole("tab", { name: "Natural language" }).click();
  await page.locator("#example-select").selectOption("__free__");
  await page
    .locator("#free-first")
    .fill("I need a durable leather belt for jeans");
  await page.getByRole("button", { name: "Run" }).click();
  await waitForStages();
  await page.getByRole("heading", { name: /Closest semantic match/i }).waitFor();
  const chosenMatches = await page.locator(".match-row.chosen").count();
  if (chosenMatches < 1) {
    throw new Error("Semantic stage shows no chosen keyword matches");
  }
  const canonical = await page.locator(".canonical-message").textContent();
  if (!canonical || !canonical.includes("looking for")) {
    throw new Error(`No canonical protocol message rendered: ${canonical}`);
  }
  if ((await page.locator(".target-banner").count()) !== 0) {
    throw new Error("Free typing must not show a target banner");
  }
  surfaced.push(
    `natural language: free text mapped to "${canonical.trim().slice(0, 80)}" via the semantic stage`,
  );
  await page.screenshot({ path: shot("05-natural-semantic"), fullPage: true });

  const fatal = errors.filter((entry) => !/favicon|fonts.googleapis|fonts.gstatic|net::ERR/i.test(entry));
  if (fatal.length) {
    throw new Error(`Browser console errors:\n${fatal.join("\n")}`);
  }
  process.stdout.write("E2E passed. Surfaced cases:\n");
  for (const line of surfaced) {
    process.stdout.write(`  - ${line}\n`);
  }
} finally {
  await browser.close();
}
