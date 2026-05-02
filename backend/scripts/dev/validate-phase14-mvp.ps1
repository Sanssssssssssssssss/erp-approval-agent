param(
  [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
Set-Location $RepoRoot

$Python = Join-Path $RepoRoot "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
  throw "Expected backend virtualenv python at $Python"
}

$ErpTests = @(
  "backend.tests.test_erp_approval_domain",
  "backend.tests.test_erp_approval_routing",
  "backend.tests.test_erp_approval_edges",
  "backend.tests.test_erp_approval_context_adapter",
  "backend.tests.test_erp_approval_graph_smoke",
  "backend.tests.test_erp_approval_hitl_gate",
  "backend.tests.test_erp_approval_action_proposals",
  "backend.tests.test_erp_approval_trace_store",
  "backend.tests.test_erp_approval_analytics",
  "backend.tests.test_erp_approval_api",
  "backend.tests.test_erp_approval_proposal_ledger",
  "backend.tests.test_erp_approval_audit_package",
  "backend.tests.test_erp_approval_audit_workspace",
  "backend.tests.test_erp_approval_action_simulation",
  "backend.tests.test_erp_approval_connectors",
  "backend.tests.test_erp_approval_connector_config",
  "backend.tests.test_erp_approval_connector_api",
  "backend.tests.test_erp_approval_connector_replay",
  "backend.tests.test_erp_approval_connector_coverage",
  "backend.tests.test_erp_approval_release_boundary",
  "backend.tests.test_erp_approval_case_file",
  "backend.tests.test_erp_approval_evidence_requirements",
  "backend.tests.test_erp_approval_evidence_claims",
  "backend.tests.test_erp_approval_evidence_sufficiency",
  "backend.tests.test_erp_approval_control_matrix",
  "backend.tests.test_erp_approval_case_review",
  "backend.tests.test_erp_approval_case_graph"
)

$LegacyTests = @(
  "backend.tests.test_retrieval_strategy",
  "backend.tests.test_rfp_security_domain",
  "backend.tests.test_rfp_security_benchmark",
  "backend.tests.test_benchmark_evaluator"
)

Write-Host "Running ERP approval MVP test suite..."
& $Python -m unittest @ErpTests

Write-Host "Running legacy RFP/security compatibility tests..."
& $Python -m unittest @LegacyTests

Write-Host "Running py_compile on Phase 14 touched Python files..."
$CompileScript = @'
import py_compile

files = [
    "src/backend/domains/erp_approval/case_models.py",
    "src/backend/domains/erp_approval/evidence_requirements.py",
    "src/backend/domains/erp_approval/evidence_claims.py",
    "src/backend/domains/erp_approval/evidence_sufficiency.py",
    "src/backend/domains/erp_approval/control_matrix.py",
    "src/backend/domains/erp_approval/case_review.py",
    "src/backend/domains/erp_approval/__init__.py",
    "src/backend/orchestration/compiler.py",
    "src/backend/orchestration/executor.py",
    "src/backend/orchestration/nodes/__init__.py",
    "src/backend/orchestration/nodes/erp_approval.py",
    "src/backend/orchestration/state.py",
    "backend/tests/test_erp_approval_case_file.py",
    "backend/tests/test_erp_approval_evidence_requirements.py",
    "backend/tests/test_erp_approval_evidence_claims.py",
    "backend/tests/test_erp_approval_evidence_sufficiency.py",
    "backend/tests/test_erp_approval_control_matrix.py",
    "backend/tests/test_erp_approval_case_review.py",
    "backend/tests/test_erp_approval_case_graph.py",
    "backend/tests/test_erp_approval_connector_config.py",
    "backend/tests/test_erp_approval_release_boundary.py",
]
for file in files:
    py_compile.compile(file, doraise=True)
print(f"py_compile ok: {len(files)} files")
'@
$CompileScript | & $Python -

Write-Host "Running LangGraph compiler smoke..."
$CompilerSmoke = @'
from src.backend.orchestration.compiler import compile_harness_orchestration_graph

class DummyOrchestrator:
    pass

compiled = compile_harness_orchestration_graph(DummyOrchestrator(), include_checkpointer=False)
print(type(compiled).__name__)
'@
$CompilerSmoke | & $Python -

if (-not $SkipFrontend) {
  Write-Host "Running frontend build..."
  Push-Location (Join-Path $RepoRoot "src\frontend")
  try {
    npm run build
  } finally {
    Pop-Location
  }
}

Write-Host "Running git diff --check..."
git diff --check

Write-Host "Phase 14 MVP validation completed."
