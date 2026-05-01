import { mkdir } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const uiBaseUrl = process.env.UI_BASE_URL || "http://127.0.0.1:3000";
const apiBaseUrl = process.env.API_BASE_URL || "http://127.0.0.1:8015/api";
const screenshotDir = path.resolve(process.cwd(), "output/playwright");

async function ensureVisible(locator, label, timeout = 30000) {
  await locator.waitFor({ state: "visible", timeout });
  if (!(await locator.isVisible())) {
    throw new Error(`${label} is not visible`);
  }
}

async function createFreshSession() {
  const title = `UX HITL 验证 ${Date.now()}`;
  const response = await fetch(`${apiBaseUrl}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title })
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Failed to create UX verification session: ${response.status} ${body}`);
  }

  return response.json();
}

async function scrollActivePanel(page) {
  await page.evaluate(() => {
    const candidates = Array.from(document.querySelectorAll(".overflow-y-auto"));
    const scrollable = candidates.find((node) => node.scrollHeight > node.clientHeight + 8);
    if (scrollable) {
      scrollable.scrollTop = Math.min(scrollable.scrollHeight, scrollable.scrollTop + 900);
    }
  });
  await page.waitForTimeout(350);
  await page.evaluate(() => {
    const candidates = Array.from(document.querySelectorAll(".overflow-y-auto"));
    const scrollable = candidates.find((node) => node.scrollHeight > node.clientHeight + 8);
    if (scrollable) {
      scrollable.scrollTop = 0;
    }
  });
  await page.waitForTimeout(250);
}

async function hasHorizontalOverflow(page) {
  return page.evaluate(() => {
    const viewportWidth = document.documentElement.clientWidth;
    const bodyOverflow = document.body.scrollWidth - viewportWidth;
    const docOverflow = document.documentElement.scrollWidth - viewportWidth;
    return Math.max(bodyOverflow, docOverflow) > 4;
  });
}

async function main() {
  await mkdir(screenshotDir, { recursive: true });
  const session = await createFreshSession();
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.addInitScript(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
  });

  try {
    await page.goto(uiBaseUrl, { waitUntil: "networkidle" });
    await ensureVisible(page.getByText(session.title).first(), "fresh UX verification session");
    await ensureVisible(page.getByRole("button", { name: /审批助理/ }).first(), "审批助理 tab");
    await page.screenshot({ fullPage: true, path: path.join(screenshotDir, "frontend-ux-chat-desktop.png") });

    const prompt =
      "请审核采购申请 PR-1001，申请部门 Operations，金额 24500 USD，供应商 Acme Supplies，成本中心 OPS-CC-10，用途是 replacement laptops。请给出审批建议、风险点、缺失信息和下一步建议。";
    await page.getByRole("textbox").first().fill(prompt);
    await page.getByRole("button", { name: /开始审查/ }).click();
    await ensureVisible(page.getByText(/先看清建议，再决定是否采用/).first(), "ERP HITL recommendation preview", 120000);
    await ensureVisible(page.getByText(/Agent 当前建议/).first(), "ERP recommendation summary", 30000);
    await ensureVisible(page.getByText(/需要补充信息|建议通过|建议拒绝|升级人工复核|已阻断/).first(), "ERP recommendation status", 30000);
    await ensureVisible(page.getByRole("button", { name: /采用这条建议并继续/ }).first(), "HITL accept button");
    await ensureVisible(page.getByRole("button", { name: /拒绝这条建议/ }).first(), "HITL reject button");
    await page.screenshot({ fullPage: true, path: path.join(screenshotDir, "frontend-ux-hitl-review.png") });

    const payloadToggle = page.getByText("高级：查看或编辑结构化建议 JSON").first();
    await payloadToggle.click();
    await ensureVisible(page.getByRole("button", { name: /保存 JSON 编辑并继续/ }).first(), "HITL edit button");
    await page.screenshot({ fullPage: true, path: path.join(screenshotDir, "frontend-ux-hitl-expanded.png") });

    await page.getByRole("button", { name: /采用这条建议并继续/ }).first().click();
    await ensureVisible(page.getByText(/HITL 复核回执/).first(), "HITL acceptance receipt", 120000);
    await ensureVisible(page.getByText(/未执行任何 ERP|未执行 ERP|No ERP write action was executed/).first(), "ERP non-action statement", 30000);
    await page.screenshot({ fullPage: true, path: path.join(screenshotDir, "frontend-ux-hitl-accepted.png") });

    const bodyText = await page.locator("body").innerText();
    const badFragments = [
      "ERP approval recommendation",
      "Status: request_more_info",
      "Human review required: yes",
      "PR-100 missing"
    ];
    const leakedFragment = badFragments.find((fragment) => bodyText.includes(fragment));
    if (leakedFragment) {
      throw new Error(`Unexpected untranslated or stale HITL answer fragment: ${leakedFragment}`);
    }

    await page.getByRole("button", { name: /管理洞察/ }).click();
    await ensureVisible(page.getByText(/只读 ERP 审批 Trace Explorer|管理洞察/).first(), "管理洞察 panel");
    await scrollActivePanel(page);
    await page.screenshot({ fullPage: true, path: path.join(screenshotDir, "frontend-ux-insights.png") });

    await page.getByRole("button", { name: /Audit Trace/ }).click();
    await ensureVisible(page.getByRole("button", { name: /模型可见上下文/ }), "Audit Trace context button");
    await scrollActivePanel(page);
    await page.screenshot({ fullPage: true, path: path.join(screenshotDir, "frontend-ux-trace.png") });

    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(400);
    await page.getByRole("button", { name: /审批助理/ }).click();
    await page.screenshot({ fullPage: true, path: path.join(screenshotDir, "frontend-ux-chat-mobile.png") });

    const verification = {
      pass: !(await hasHorizontalOverflow(page)),
      screenshots: [
        path.join(screenshotDir, "frontend-ux-chat-desktop.png"),
        path.join(screenshotDir, "frontend-ux-hitl-review.png"),
        path.join(screenshotDir, "frontend-ux-hitl-expanded.png"),
        path.join(screenshotDir, "frontend-ux-hitl-accepted.png"),
        path.join(screenshotDir, "frontend-ux-insights.png"),
        path.join(screenshotDir, "frontend-ux-trace.png"),
        path.join(screenshotDir, "frontend-ux-chat-mobile.png")
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
