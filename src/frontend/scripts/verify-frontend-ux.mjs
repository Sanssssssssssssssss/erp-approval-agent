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
  "Amount: USD 24500",
  "Item: replacement laptops",
  "Price basis: preferred supplier quote",
  "This is fictional local text evidence for UI verification only."
].join("\n");

function fail(message) {
  throw new Error(message);
}

async function ensureVisible(locator, label, timeout = 30000) {
  await locator.waitFor({ state: "visible", timeout });
  if (!(await locator.isVisible())) {
    fail(`${label} is not visible`);
  }
}

async function ensureAtLeast(page, selector, minimum, label) {
  const count = await page.locator(selector).count();
  if (count < minimum) {
    fail(`${label} expected at least ${minimum}, got ${count}`);
  }
}

async function horizontalOverflow(page) {
  return page.evaluate(() => {
    const viewportWidth = document.documentElement.clientWidth;
    const bodyOverflow = document.body.scrollWidth - viewportWidth;
    const docOverflow = document.documentElement.scrollWidth - viewportWidth;
    return Math.max(bodyOverflow, docOverflow);
  });
}

function noWriteStatement(payload) {
  return String(payload.non_action_statement || payload.review?.non_action_statement || "");
}

async function submitCaseTurn(page, label) {
  const responsePromise = page.waitForResponse(
    (response) => response.url().includes("/erp-approval/cases/turn") && response.status() === 200,
    { timeout: 300000 }
  );
  const submitButton = page.locator(".case-agent-composer-actions button.ui-button-primary");
  await ensureVisible(submitButton, `${label} submit button`);
  await submitButton.click();
  const response = await responsePromise;
  const payload = await response.json();
  await page.locator(".case-agent-message-agent").last().waitFor({ state: "visible", timeout: 30000 });
  if (!payload?.review?.recommendation?.status) {
    fail(`${label} did not return a structured recommendation`);
  }
  if (!noWriteStatement(payload).includes("No ERP write action was executed")) {
    fail(`${label} missed the no-ERP-write boundary`);
  }
  return payload;
}

async function scrollMainPanel(page) {
  await page.evaluate(() => {
    const candidates = Array.from(document.querySelectorAll(".case-agent-chat, .case-agent-side, main"));
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
    await ensureVisible(page.locator(".case-agent-page"), "case agent workspace");
    await ensureVisible(page.locator(".case-agent-main"), "case agent main panel");
    await ensureVisible(page.locator(".case-agent-side-empty"), "empty side panel");
    await ensureVisible(page.locator(".case-agent-composer"), "case composer");
    await ensureAtLeast(page, ".case-agent-message", 1, "initial chat messages");
    await page.screenshot({ fullPage: true, path: path.join(screenshotDir, "01-empty-agent-workspace.png") });

    await page.locator(".case-agent-composer > textarea").fill(REQUEST_TEXT);
    await page.locator("input[type='file']").setInputFiles(evidencePath);
    await ensureVisible(page.locator(".case-agent-evidence-queue"), "queued file evidence");
    const payload = await submitCaseTurn(page, "case workspace turn");
    if (!payload.case_state?.case_id) {
      fail("case workspace turn did not create a case state");
    }
    if (payload.review.recommendation.status === "recommend_approve") {
      fail("initial workspace turn recommended approval without a full evidence set");
    }

    await ensureVisible(page.locator(".case-agent-side-section").first(), "case side details");
    await ensureVisible(page.locator(".case-agent-progress"), "evidence completeness progress");
    await ensureAtLeast(page, ".case-agent-message", 3, "chat messages after first turn");
    await page.screenshot({ fullPage: true, path: path.join(screenshotDir, "02-case-workspace-desktop.png") });

    await scrollMainPanel(page);
    await page.screenshot({ fullPage: true, path: path.join(screenshotDir, "03-case-workspace-scrolled.png") });

    for (const [index, name] of [
      [1, "04-case-workspace-trace.png"],
      [2, "05-case-workspace-assets.png"],
      [3, "06-case-workspace-insights.png"]
    ]) {
      await page.locator(".workspace-tab").nth(index).click();
      await page.waitForTimeout(700);
      await page.screenshot({ fullPage: true, path: path.join(screenshotDir, name) });
    }

    await page.locator(".workspace-tab").first().click();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(500);
    await ensureVisible(page.locator(".case-agent-page"), "mobile case workspace");
    await page.screenshot({ fullPage: true, path: path.join(screenshotDir, "07-case-workspace-mobile.png") });

    const overflow = await horizontalOverflow(page);
    const verification = {
      pass: overflow <= 4 && consoleErrors.length === 0 && pageErrors.length === 0 && failedRequests.length === 0,
      screenshots: screenshotDir,
      horizontalOverflow: overflow,
      consoleErrors,
      pageErrors,
      failedRequests,
      case_id: payload.case_state.case_id,
      status: payload.review.recommendation.status
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
