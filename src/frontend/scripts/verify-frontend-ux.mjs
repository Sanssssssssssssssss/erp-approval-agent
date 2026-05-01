import { mkdir } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const uiBaseUrl = process.env.UI_BASE_URL || "http://127.0.0.1:3000";
const screenshotDir = path.resolve(process.cwd(), "output/playwright");

async function ensureVisible(locator, label) {
  await locator.waitFor({ state: "visible", timeout: 30000 });
  if (!(await locator.isVisible())) {
    throw new Error(`${label} is not visible`);
  }
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
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

  try {
    await page.goto(uiBaseUrl, { waitUntil: "networkidle" });
    await ensureVisible(page.getByRole("button", { name: /审批助理/ }), "审批助理 tab");
    await page.screenshot({ fullPage: true, path: path.join(screenshotDir, "frontend-ux-chat-desktop.png") });

    const payloadToggle = page.getByText("高级：查看或编辑结构化建议 JSON").first();
    if (await payloadToggle.count()) {
      await payloadToggle.click();
      await ensureVisible(page.getByRole("button", { name: /采用建议并继续|通过复核/ }).first(), "HITL accept button");
      await ensureVisible(page.getByRole("button", { name: /拒绝这条建议|拒绝/ }).first(), "HITL reject button");
      await ensureVisible(page.getByRole("button", { name: /保存 JSON 编辑并继续/ }).first(), "HITL edit button");
      await page.screenshot({ fullPage: true, path: path.join(screenshotDir, "frontend-ux-hitl-expanded.png") });
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
        path.join(screenshotDir, "frontend-ux-hitl-expanded.png"),
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
