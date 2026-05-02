import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const uiBaseUrl = process.env.UI_BASE_URL || "http://127.0.0.1:3000";
const screenshotDir = path.resolve(process.cwd(), "output/playwright/case-workspace");

const REQUEST_TEXT =
  "Create purchase requisition case PR-UX-001. Department Operations. Amount 24500 USD. Vendor Acme Supplies. Cost center OPS-CC-10. Purpose replacement laptops. First create the case and list missing evidence. No ERP write action.";

const QUOTE_FILE = [
  "Quote Q-PR-UX-001",
  "Supplier: Acme Supplies",
  "Amount: USD 24,500",
  "Purpose: replacement laptops",
  "This is fictional local text evidence for UI verification only."
].join("\n");

async function ensureVisible(locator, label, timeout = 30000) {
  await locator.waitFor({ state: "visible", timeout });
  if (!(await locator.isVisible())) {
    throw new Error(`${label} is not visible`);
  }
}

async function ensureAtLeast(page, selector, minimum, label) {
  const count = await page.locator(selector).count();
  if (count < minimum) {
    throw new Error(`${label} expected at least ${minimum}, got ${count}`);
  }
}

async function hasHorizontalOverflow(page) {
  return page.evaluate(() => {
    const viewportWidth = document.documentElement.clientWidth;
    const bodyOverflow = document.body.scrollWidth - viewportWidth;
    const docOverflow = document.documentElement.scrollWidth - viewportWidth;
    return Math.max(bodyOverflow, docOverflow) > 4;
  });
}

async function submitCaseTurn(page, label) {
  const responsePromise = page.waitForResponse(
    (response) => response.url().includes("/erp-approval/cases/turn") && response.status() === 200,
    { timeout: 120000 }
  );
  await page.locator("button.ui-button-primary").click();
  const response = await responsePromise;
  const payload = await response.json();
  await page.locator("button.ui-button-primary").waitFor({ state: "visible", timeout: 30000 });
  if (!payload?.review?.recommendation) {
    throw new Error(`${label} did not return a structured recommendation`);
  }
  if (!String(payload.non_action_statement || payload.review?.non_action_statement || "").includes("No ERP write action was executed")) {
    throw new Error(`${label} missed the no-ERP-write boundary`);
  }
  return payload;
}

async function scrollMainPanel(page) {
  await page.evaluate(() => {
    const candidates = Array.from(document.querySelectorAll(".case-review-output, .overflow-y-auto, main"));
    const scrollable = candidates.find((node) => node.scrollHeight > node.clientHeight + 8);
    if (scrollable) {
      scrollable.scrollTop = Math.min(scrollable.scrollHeight, scrollable.scrollTop + 900);
    }
  });
  await page.waitForTimeout(300);
}

async function main() {
  await mkdir(screenshotDir, { recursive: true });
  const evidencePath = path.join(screenshotDir, "case-workspace-quote-evidence.txt");
  await writeFile(evidencePath, QUOTE_FILE, "utf8");

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const consoleErrors = [];
  const pageErrors = [];
  const failedRequests = [];

  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push(message.text());
    }
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("requestfailed", (request) => {
    const url = request.url();
    if (!url.includes("/_next/static/") && !url.includes("favicon")) {
      failedRequests.push(`${request.method()} ${url}: ${request.failure()?.errorText || "failed"}`);
    }
  });

  await page.addInitScript(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  try {
    await page.goto(uiBaseUrl, { waitUntil: "networkidle", timeout: 90000 });
    await ensureVisible(page.locator(".case-review-page"), "case workspace");
    await ensureVisible(page.locator(".case-review-empty"), "empty case state");
    await ensureAtLeast(page, ".case-input-group", 3, "left input groups");
    await page.screenshot({ fullPage: true, path: path.join(screenshotDir, "01-empty-grouped-workspace.png") });

    await page.locator("textarea").first().fill(REQUEST_TEXT);
    await page.locator("input[type='file']").setInputFiles(evidencePath);
    const payload = await submitCaseTurn(page, "case workspace turn");
    if (payload.review.recommendation.status === "recommend_approve") {
      throw new Error("initial grouped workspace turn recommended approval without enough evidence");
    }

    await ensureVisible(page.locator(".case-state-machine"), "case state machine");
    await ensureVisible(page.locator(".case-review-hero"), "case review conclusion");
    await ensureVisible(page.locator(".case-checklist").first(), "required evidence checklist");
    await ensureVisible(page.locator(".case-review-memo"), "reviewer memo");
    await ensureAtLeast(page, ".case-workspace-group", 3, "right workspace groups");
    await page.screenshot({ fullPage: true, path: path.join(screenshotDir, "02-case-workspace-desktop.png") });

    await scrollMainPanel(page);
    await page.screenshot({ fullPage: true, path: path.join(screenshotDir, "03-case-workspace-scrolled.png") });

    await page.locator(".workspace-tab").nth(1).click();
    await page.waitForTimeout(500);
    await page.screenshot({ fullPage: true, path: path.join(screenshotDir, "04-case-workspace-trace.png") });

    await page.locator(".workspace-tab").nth(0).click();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(500);
    await ensureVisible(page.locator(".case-review-page"), "mobile case workspace");
    await page.screenshot({ fullPage: true, path: path.join(screenshotDir, "05-case-workspace-mobile.png") });

    const verification = {
      pass: !(await hasHorizontalOverflow(page)) && consoleErrors.length === 0 && pageErrors.length === 0 && failedRequests.length === 0,
      screenshots: screenshotDir,
      horizontalOverflow: await hasHorizontalOverflow(page),
      consoleErrors,
      pageErrors,
      failedRequests
    };
    console.log(JSON.stringify(verification, null, 2));
    if (!verification.pass) {
      process.exitCode = 1;
    }
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
