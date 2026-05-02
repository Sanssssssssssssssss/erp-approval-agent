import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const apiBaseUrl = process.env.API_BASE_URL || "http://127.0.0.1:8015/api";
const outputDir = path.resolve(process.cwd(), "output/evaluations");

const CASES = [
  {
    id: "pr_complete",
    title: "完整采购申请",
    message:
      "请审核采购申请 PR-1001，申请部门 Operations，金额 24500 USD，供应商 Acme Supplies，成本中心 OPS-CC-10，用途是 replacement laptops。请给出审批建议、风险点、缺失信息和下一步建议。",
    expect: {
      erp: true,
      approvalId: "PR-1001",
      acceptableStatuses: ["recommend_approve", "escalate"],
      requiredCitations: ["mock_erp://approval_request/PR-1001", "mock_erp://vendor/acme-supplies", "mock_erp://budget/OPS-CC-10"],
      requiredText: ["预算", "供应商", "Operations"],
      forbiddenText: ["PR-100 ", "acme-suplies", "requester 字段为空"]
    }
  },
  {
    id: "pr_unknown",
    title: "未知采购申请",
    message:
      "请审核采购申请 PR-9999，金额 98000 USD，供应商 Unknown Vendor，用途是 emergency hardware，但没有成本中心和预算信息。",
    expect: {
      erp: true,
      approvalId: "PR-9999",
      acceptableStatuses: ["request_more_info", "escalate", "blocked"],
      requiredText: ["成本中心", "预算", "供应商"],
      forbiddenText: ["PR-999 ", "9800 USD", "建议通过"]
    }
  },
  {
    id: "expense_complete",
    title: "费用报销",
    message:
      "请审核费用报销 EXP-2001，申请人 Maya Ortiz，部门 Sales，金额 842 USD，用途是 client travel，请判断是否缺资料。",
    expect: {
      erp: true,
      approvalId: "EXP-2001",
      acceptableStatuses: ["recommend_approve", "request_more_info", "escalate"],
      requiredCitations: ["mock_erp://approval_request/EXP-2001", "mock_policy://expense_policy"],
      requiredText: ["收据", "差旅"]
    }
  },
  {
    id: "invoice_match",
    title: "发票三单匹配",
    message:
      "请审核发票付款 INV-3001，供应商 Northwind Components，金额 18000 USD，请检查 PO、GRN、invoice 三单匹配并给建议。",
    expect: {
      erp: true,
      approvalId: "INV-3001",
      acceptableStatuses: ["recommend_approve", "escalate"],
      requiredCitations: ["mock_erp://purchase_order/PO-7788", "mock_erp://goods_receipt/GRN-8899", "mock_erp://invoice/INV-3001"],
      requiredText: ["PO", "GRN", "invoice"]
    }
  },
  {
    id: "supplier_pending",
    title: "供应商准入待确认",
    message:
      "请审核供应商准入 VEND-4001，供应商 BrightPath Logistics，请关注税务、银行、制裁检查是否可以通过。",
    expect: {
      erp: true,
      approvalId: "VEND-4001",
      acceptableStatuses: ["request_more_info", "escalate", "blocked"],
      requiredText: ["制裁", "税", "银行"],
      forbiddenText: ["建议通过"]
    }
  },
  {
    id: "contract_exception",
    title: "合同例外",
    message:
      "请审核合同例外 CON-5001，客户要求非标准责任上限和终止条款例外，请给出建议。",
    expect: {
      erp: true,
      approvalId: "CON-5001",
      acceptableStatuses: ["escalate", "request_more_info", "blocked"],
      requiredCitations: ["mock_erp://contract/CON-5001"],
      requiredText: ["法务", "责任", "条款"],
      forbiddenText: ["模型输出没有符合"]
    }
  },
  {
    id: "budget_exception",
    title: "预算例外",
    message:
      "请审核预算例外 BUD-6001，金额 55000 USD，成本中心 FIN-CC-77，用于 accelerated implementation support。",
    expect: {
      erp: true,
      approvalId: "BUD-6001",
      acceptableStatuses: ["escalate", "recommend_reject", "request_more_info", "blocked"],
      requiredCitations: ["mock_erp://budget/FIN-CC-77"],
      requiredText: ["资金不足", "财务"],
      forbiddenText: ["approval_type 标记为unknown"]
    }
  },
  {
    id: "ambiguous_approval",
    title: "模糊审批问题",
    message: "这个审批能过吗？",
    expect: {
      erp: true,
      acceptableStatuses: ["request_more_info", "escalate", "blocked"],
      requiredText: ["审批单", "缺少", "信息"],
      forbiddenText: ["我看到您发送的是问号"]
    }
  },
  {
    id: "workspace_search",
    title: "项目文件搜索不应被审批劫持",
    message: "请在项目里搜索 invoice_payment_policy 在哪些文件里出现，不要走审批判断。",
    expect: {
      erp: false,
      requiredText: ["invoice_payment_policy"],
      forbiddenText: ["ERP 审批建议复核"]
    }
  }
];

async function request(pathname, payload, method = payload ? "POST" : "GET") {
  const response = await fetch(`${apiBaseUrl}${pathname}`, {
    method,
    headers: payload ? { "Content-Type": "application/json" } : undefined,
    body: payload ? JSON.stringify(payload) : undefined
  });
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`${method} ${pathname} failed: ${response.status} ${text}`);
  }
  return text ? JSON.parse(text) : null;
}

function includesAny(haystack, needles = []) {
  return needles.filter((needle) => haystack.includes(needle));
}

function parseRecommendationFromAnswer(answer = "") {
  if (!answer.includes("ERP 审批建议")) {
    return null;
  }
  const statusLabel = answer.match(/当前建议：([^\n]+)/)?.[1]?.trim() || "";
  const statusMap = new Map([
    ["建议通过", "recommend_approve"],
    ["建议拒绝", "recommend_reject"],
    ["需要补充信息", "request_more_info"],
    ["升级人工复核", "escalate"],
    ["已阻断", "blocked"]
  ]);
  const citations = Array.from(
    new Set(answer.match(/mock_(?:erp|policy):\/\/[A-Za-z0-9_\-/.]+/g) || [])
  );
  return {
    status: statusMap.get(statusLabel) || "",
    summary: answer,
    rationale: [],
    missing_information: [],
    risk_flags: [],
    citations
  };
}

function parseApprovalRequestFromAnswer(answer = "") {
  const fromApprovalLine = answer.match(/审批单：[^/\n]+\/\s*([A-Z]+-\d+)/)?.[1] || "";
  const fallback = answer.match(/\b(?:PR|PO|EXP|INV|VEND|CON|BUD)-\d+\b/)?.[0] || "";
  const approvalId = fromApprovalLine || fallback;
  return approvalId ? { approval_id: approvalId } : null;
}

function scoreCase(result, expectation) {
  const issues = [];
  const fullText = [
    result.answer || "",
    result.recommendation?.summary || "",
    ...(result.recommendation?.rationale || []),
    ...(result.recommendation?.missing_information || []),
    ...(result.recommendation?.risk_flags || []),
    ...(result.guard?.warnings || []),
    ...(result.recommendation?.citations || [])
  ].join("\n");

  if (expectation.erp && !result.hasErp) {
    issues.push("没有进入 ERP approval graph / 生成 ERP 审批建议");
  }
  if (!expectation.erp && result.hasErp) {
    issues.push("非审批请求被 ERP approval graph 劫持");
  }
  if (expectation.approvalId) {
    const requestId = result.approvalRequest?.approval_id || "";
    if (requestId !== expectation.approvalId) {
      issues.push(`approval_id 解析错误：期望 ${expectation.approvalId}，实际 ${requestId || "空"}`);
    }
  }
  if (expectation.acceptableStatuses?.length && result.recommendation) {
    const status = result.recommendation.status || "";
    if (!expectation.acceptableStatuses.includes(status)) {
      issues.push(`建议状态不合理：${status || "空"}`);
    }
  }
  for (const sourceId of expectation.requiredCitations || []) {
    if (!(result.recommendation?.citations || []).includes(sourceId)) {
      issues.push(`缺少关键 citation：${sourceId}`);
    }
  }
  for (const phrase of expectation.requiredText || []) {
    if (!fullText.includes(phrase)) {
      issues.push(`缺少关键判断文字：${phrase}`);
    }
  }
  for (const phrase of expectation.forbiddenText || []) {
    if (fullText.includes(phrase)) {
      issues.push(`出现不应出现的文字：${phrase}`);
    }
  }

  const score = Math.max(0, 100 - issues.length * 15);
  return { score, issues };
}

async function runCase(testCase) {
  const session = await request("/sessions", { title: `质量评测 ${testCase.id} ${Date.now()}` });
  const chat = await request("/chat", {
    session_id: session.id,
    message: testCase.message,
    stream: false
  });
  const hitl = await request(`/sessions/${encodeURIComponent(session.id)}/hitl`);
  const latest = hitl.requests?.at(-1)?.request || null;
  const proposed = latest?.proposed_input || {};
  const recommendation = proposed.recommendation || parseRecommendationFromAnswer(chat?.content || "");
  const approvalRequest = proposed.approval_request || parseApprovalRequestFromAnswer(chat?.content || "");
  const guard = proposed.guard_result || null;
  const result = {
    id: testCase.id,
    title: testCase.title,
    sessionId: session.id,
    hasHitl: Boolean(latest),
    hasErp: Boolean(latest) || Boolean(recommendation),
    capabilityId: latest?.capability_id || "",
    approvalRequest,
    recommendation,
    guard,
    answer: chat?.content || ""
  };
  return { ...result, ...scoreCase(result, testCase.expect) };
}

async function main() {
  await mkdir(outputDir, { recursive: true });
  const results = [];
  for (const testCase of CASES) {
    try {
      const result = await runCase(testCase);
      results.push(result);
      const status = result.recommendation?.status || (result.hasHitl ? "pending" : "non_erp");
      console.log(`${result.score.toString().padStart(3)}  ${result.id.padEnd(20)} ${status}`);
      for (const issue of result.issues) {
        console.log(`     - ${issue}`);
      }
    } catch (error) {
      const failed = {
        id: testCase.id,
        title: testCase.title,
        score: 0,
        issues: [error instanceof Error ? error.message : String(error)]
      };
      results.push(failed);
      console.log(`  0  ${testCase.id.padEnd(20)} ERROR`);
      console.log(`     - ${failed.issues[0]}`);
    }
  }

  const averageScore = Math.round(results.reduce((sum, item) => sum + item.score, 0) / results.length);
  const report = {
    generatedAt: new Date().toISOString(),
    apiBaseUrl,
    averageScore,
    pass: averageScore >= 80 && results.every((item) => item.score >= 70),
    results
  };
  const reportPath = path.join(outputDir, "erp-agent-quality-latest.json");
  await writeFile(reportPath, JSON.stringify(report, null, 2), "utf8");
  console.log(JSON.stringify({ averageScore, pass: report.pass, reportPath }, null, 2));
  if (!report.pass) {
    process.exitCode = 1;
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
