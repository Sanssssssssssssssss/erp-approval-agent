import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const uiBaseUrl = process.env.UI_BASE_URL || "http://127.0.0.1:3000";
const screenshotDir = path.resolve(process.cwd(), "output/playwright");

async function ensureVisible(locator, label, timeout = 30000) {
  await locator.waitFor({ state: "visible", timeout });
  if (!(await locator.isVisible())) {
    throw new Error(`${label} is not visible`);
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

async function scrollMainPanel(page) {
  await page.evaluate(() => {
    const candidates = Array.from(document.querySelectorAll(".case-review-output, .overflow-y-auto"));
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
  await writeFile(
    evidencePath,
    [
      "Quote Q-PR-UX-001",
      "Supplier: Acme Supplies",
      "Amount: USD 24,500",
      "Purpose: replacement laptops",
      "This is fictional local text evidence for UI verification only."
    ].join("\n"),
    "utf8"
  );

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.addInitScript(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  try {
    await page.goto(uiBaseUrl, { waitUntil: "networkidle" });
    await ensureVisible(page.locator(".case-review-page"), "case workspace");
    await ensureVisible(page.locator(".case-review-empty"), "empty case state");

    const initialBody = await page.locator("body").innerText();
    if (initialBody.includes("聊天流") || initialBody.includes("审批助理")) {
      throw new Error("Old chat assistant entry is still visible in the default workspace");
    }

    await page.locator("textarea").first().fill(
      "请审核采购申请 PR-UX-001，申请部门 Operations，金额 24500 USD，供应商 Acme Supplies，成本中心 OPS-CC-10。先创建案卷并列出缺失证据。"
    );
    await page.locator("input[type='file']").setInputFiles(evidencePath);
    await page.locator("button.ui-button-primary").click();

    await ensureVisible(page.locator(".case-state-machine"), "case state machine", 120000);
    await ensureVisible(page.locator(".case-review-hero"), "case review conclusion");
    await ensureVisible(page.locator(".case-checklist").first(), "required evidence checklist");
    await ensureVisible(page.locator(".case-review-memo"), "reviewer memo");
    await page.screenshot({ fullPage: true, path: path.join(screenshotDir, "case-workspace-desktop.png") });

    await scrollMainPanel(page);
    await page.screenshot({ fullPage: true, path: path.join(screenshotDir, "case-workspace-scrolled.png") });

    await page.getByRole("button", { name: "Audit Trace" }).click();
    await ensureVisible(page.locator("body").getByText(/Audit Trace|上下文|模型/).first(), "audit trace panel");
    await page.screenshot({ fullPage: true, path: path.join(screenshotDir, "case-workspace-trace.png") });

    await page.locator(".workspace-tab").nth(0).click();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(400);
    await ensureVisible(page.locator(".case-review-page"), "mobile case workspace");
    await page.screenshot({ fullPage: true, path: path.join(screenshotDir, "case-workspace-mobile.png") });

    const verification = {
      pass: !(await hasHorizontalOverflow(page)),
      screenshots: [
        path.join(screenshotDir, "case-workspace-desktop.png"),
        path.join(screenshotDir, "case-workspace-scrolled.png"),
        path.join(screenshotDir, "case-workspace-trace.png"),
        path.join(screenshotDir, "case-workspace-mobile.png")
      ],
      horizontalOverflow: await hasHorizontalOverflow(page)
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
