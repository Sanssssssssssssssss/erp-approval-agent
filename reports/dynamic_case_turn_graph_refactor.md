# Dynamic Case-Turn Graph Refactor

## 摘要

本次改造把 `/api/erp-approval/cases/turn` 背后的案卷流程从线性 chain 改成 HarnessRuntime-owned + LangGraph conditional routing 的动态审批案卷主图。

旧图虽然已经回到 HarnessRuntime，但节点仍是固定顺序：

```text
load_case_state -> classify_turn -> assemble_case_context -> review_submission -> propose_patch -> validate_patch -> persist_case -> respond
```

这会让所有用户输入看起来都像同一种审查动作，也不利于在 trace 中看出“跑题、问状态、补证、P2P 审证、最终 memo gate”分别走了什么路径。

新图把每一轮用户输入作为一次受控 case turn：

```text
load_case_state
-> version_conflict_gate
-> classify_turn_intent
-> build_turn_contract
-> assemble_case_context
-> route_turn_intent
```

之后由 `route_turn_intent` 和 `route_evidence_type` 进入不同分支。CaseHarness 仍然只是图节点中的案卷管理模块；HarnessRuntime 仍然拥有 run lifecycle；CaseMemoryStore / CasePatchValidator / DossierWriter 仍然只在图节点内被调用。

## 新动态图拓扑

主路由：

- `ask_required_materials` -> `materials_guidance_node` -> `propose_case_patch`
- `ask_status` -> `case_status_summary_node` -> `propose_case_patch`
- `off_topic` -> `off_topic_reject_node` -> `validate_case_patch`
- `correct_previous_evidence` -> `correct_evidence_node` -> `recompute_case_analysis`
- `withdraw_evidence` -> `withdraw_evidence_node` -> `recompute_case_analysis`
- `request_final_memo` -> `final_memo_gate`
- `submit_evidence` -> `build_candidate_evidence` -> `route_evidence_type`

证据路由：

- P2P 证据：`invoice` / `purchase_order` / `goods_receipt` / `payment_terms` / `duplicate_check` / `process_log` / `clear_invoice_event`
  - 进入 `p2p_process_fact_extractor`
  - `p2p_match_type_classifier`
  - `p2p_sequence_anomaly_reviewer`
  - `p2p_amount_consistency_reviewer`
  - `p2p_exception_reviewer`
  - `p2p_patch_proposal`
  - `p2p_process_patch_validator`
- 采购申请证据：进入 `purchase_requisition_review_subgraph`
- 费用报销证据：进入 `expense_review_subgraph`
- 供应商准入证据：进入 `supplier_onboarding_review_subgraph`
- 合同例外证据：进入 `contract_exception_review_subgraph`
- 预算例外证据：进入 `budget_exception_review_subgraph`
- 未知材料：进入 `generic_evidence_review_subgraph`

所有证据分支最终进入：

```text
merge_review_outputs
-> evidence_sufficiency_gate
-> contradiction_gate
-> control_matrix_gate
-> propose_case_patch
-> validate_case_patch
-> route_patch_validity
```

有效 patch 才会进入：

```text
persist_case_state_dossier_audit -> respond_to_user
```

无效 patch 进入：

```text
reject_patch_explain -> respond_to_user
```

## LLM 角色纳入方式

`CaseStageModelReviewer` 的五个角色仍然是：

- `turn_classifier`
- `evidence_extractor`
- `policy_interpreter`
- `contradiction_reviewer`
- `reviewer_memo`

它们不再被旧的 `review_submission_node` 包成唯一审查节点，而是在各 evidence review branch 中作为 stage model patch proposal 被调用。模型输出仍只能进入 `CasePatch.model_review` 和 `branch_review_outputs`，不能直接写 `case_state.json`、`dossier.md` 或 `audit_log.jsonl`。

## Deterministic Gates

以下门禁仍由 deterministic code 控制：

- `CasePatchValidator`
- `evidence_sufficiency_gate`
- `contradiction_gate`
- `control_matrix_gate`
- no ERP write/action boundary
- source_id / claim_id / requirement_id 绑定校验
- user_statement 不能满足 blocking evidence
- accepted_evidence 必须有 source_id、claim_ids、requirement_ids

无效 patch 只写 rejection audit，不污染 accepted evidence。

## P2P Specialist Subgraph

新增：

- `src/backend/domains/erp_approval/p2p_process_models.py`
- `src/backend/domains/erp_approval/p2p_process_review.py`

P2P 输出包含：

- `match_type`
- `sequence_anomalies`
- `amount_facts`
- `process_exceptions`
- `missing_process_evidence`
- `p2p_next_questions`
- `p2p_reviewer_notes`

重点修复：

- 明确 3-way / 2-way / consignment 语义。
- 解释 invoice-before-GR 时序风险。
- 将 Clear Invoice 明确解释为历史事件，而不是 Agent 可执行付款。
- 加入 PO / invoice / GRN / cumulative net worth 金额一致性说明。
- 对 cancellation / reversal / payment block 形成风险说明。

## BPI 2019 对比

本地 BPI 2019 sample eval 使用 300 个本地样本，不访问网络，不调用真实 ERP，不执行动作。

改造前本轮基线：

- average_score: `92.53`
- false_approve: `0`
- critical: `0`
- major: `65`
- top failure: `sequence_explanation`

改造后：

- average_score: `100.00`
- false_approve: `0`
- critical: `0`
- major: `0`
- pass: `300 / 300`

结果文件：

- `reports/evaluations/bpi2019_evidence_sample_eval_latest.md`
- `reports/evaluations/bpi2019_evidence_sample_eval_latest.json`

## 仍未解决的问题

- 非 P2P specialist subgraphs 目前仍复用现有 evidence review 逻辑，只是已经成为图上的独立分支。后续可以继续把采购、费用、供应商、合同、预算分别拆成更细的 role/subgraph。
- LLM role 仍由 `CaseStageModelReviewer.review_turn` 聚合调用；它的结果已经写入 patch metadata，但还没有把五个 LLM role 拆成五个单独 LangGraph 节点。
- P2P amount extraction 是 representative local evaluator，不是生产级 OCR/ERP schema parser。

## 验证结果

已运行：

```text
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_erp_approval_dynamic_case_turn_graph backend.tests.test_erp_approval_case_review_api backend.tests.test_erp_approval_case_harness backend.tests.test_erp_approval_case_harness_p0_p1 backend.tests.test_erp_approval_case_graph backend.tests.test_erp_approval_release_boundary
```

结果：`40 tests OK`

```text
backend\.venv\Scripts\python.exe -m unittest <ERP approval full suite including dynamic graph>
```

结果：`169 tests OK`

```text
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_retrieval_strategy backend.tests.test_rfp_security_domain backend.tests.test_rfp_security_benchmark backend.tests.test_benchmark_evaluator
```

结果：`11 tests OK`

```text
backend\.venv\Scripts\python.exe -m backend.benchmarks.erp_approval_bpi2019_sample_eval --csv artifacts\downloads\bpi2019\csv\BPI_Challenge_2019.csv --limit 300 --report reports\evaluations\bpi2019_evidence_sample_eval_latest.md --json reports\evaluations\bpi2019_evidence_sample_eval_latest.json --cases-out backend\benchmarks\cases\erp_approval\bpi2019_sample_cases.json
```

结果：`bpi_cases=300 avg_score=100.00 false_approve=0 critical=0 major=0`

```text
backend\.venv\Scripts\python.exe -m py_compile <modified Python files>
```

结果：通过

```text
LangGraph compiler smoke
```

结果：`CompiledStateGraph`

```text
cd src\frontend
npm run build
```

结果：通过

```text
powershell -ExecutionPolicy Bypass -File backend\scripts\dev\validate-phase14-mvp.ps1
```

结果：通过；包含 `174 tests OK`、legacy `11 tests OK`、frontend build OK、git diff --check OK。

## 边界

本次没有新增真实 ERP connector、没有执行任何 ERP 写动作、没有新增 action execution API、没有新增 action execution ledger、没有调用 capability_invoke、没有引入 `approval.*` Harness event namespace。

## Phase 2 Dynamic Graph Enhancement

This follow-up keeps the same release boundary and tightens observability.

### Unified Graph Name

All case-turn runtime surfaces now use:

```text
erp_approval_dynamic_case_turn_graph
```

This applies to:

- `CASE_TURN_GRAPH_NAME`
- `CaseTurnExecutor` emitted payloads
- API `harness_run.graph_name`
- tests and reports

### Visible LLM Role Nodes

The stage model roles are now explicit graph nodes:

- `llm_turn_classifier`
- `llm_evidence_extractor`
- `llm_policy_interpreter`
- `llm_contradiction_reviewer`
- `llm_reviewer_memo`
- `aggregate_llm_stage_outputs`

They only write role outputs and patch metadata:

- `stage_model_role_outputs`
- `stage_model_role_errors`
- `model_decision`
- `patch.model_review`

They do not write case state, dossier, audit log, or accepted evidence directly. If no local model is configured, the nodes still appear in `graph_steps` and record a skipped role output.

### LLM-heavy P2P Review + Deterministic Gate

P2P keeps deterministic fact extraction and adds model-facing explanation nodes:

- `p2p_process_fact_explanation`
- `p2p_sequence_risk_explanation`
- `p2p_amount_reconciliation_explanation`
- `p2p_missing_evidence_questions`

The model is responsible for explaining process facts, sequence risk, amount reconciliation, and missing evidence questions. Deterministic code still gates:

- `match_type` enum validity
- candidate `source_id` boundaries
- Clear Invoice as historical event only, never execution authorization
- amount reconciliation warnings
- `No ERP write action was executed` boundary

### Phase 2 Validation

Additional validation after this enhancement:

```text
backend\.venv\Scripts\python.exe -m unittest backend.tests.test_erp_approval_dynamic_case_turn_graph backend.tests.test_erp_approval_case_review_api backend.tests.test_erp_approval_case_harness backend.tests.test_erp_approval_case_harness_p0_p1 backend.tests.test_erp_approval_case_graph backend.tests.test_erp_approval_release_boundary
```

Result: `41 tests OK`

```text
backend\.venv\Scripts\python.exe -m unittest <ERP approval full suite including dynamic graph>
```

Result: `170 tests OK`

```text
backend\.venv\Scripts\python.exe -m backend.benchmarks.erp_approval_bpi2019_sample_eval --csv artifacts\downloads\bpi2019\csv\BPI_Challenge_2019.csv --limit 300 --report reports\evaluations\bpi2019_evidence_sample_eval_latest.md --json reports\evaluations\bpi2019_evidence_sample_eval_latest.json --cases-out backend\benchmarks\cases\erp_approval\bpi2019_sample_cases.json
```

Result: `bpi_cases=300 avg_score=100.00 false_approve=0 critical=0 major=0`

LangGraph compiler smoke:

```text
erp_approval_dynamic_case_turn_graph
48
CompiledStateGraph
```
