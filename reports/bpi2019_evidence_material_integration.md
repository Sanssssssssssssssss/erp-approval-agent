# BPI 2019 Evidence Material Integration

## Summary

The BPI Challenge 2019 purchase-to-pay event log was downloaded locally and used as read-only evidence material for ERP invoice/payment case review stress testing.

This work does not connect to ERP, does not run a live connector, does not execute approval/payment/write actions, and does not claim production benchmark accuracy.

## Source

- Source page: https://icpmconference.org/2019/icpm-2019/contests-challenges/bpi-challenge-2019/
- DOI citation: https://doi.org/10.4121/uuid:d06aff4b-79f0-45e6-8ec8-e19730c248f1
- Dataset: BPI Challenge 2019 purchase-to-pay event log.
- Local raw CSV path: `artifacts/downloads/bpi2019/csv/BPI_Challenge_2019.csv`
- Raw CSV and zip are intentionally kept under ignored local `artifacts/` storage and are not committed.

## What Was Added

- `backend/benchmarks/erp_approval_bpi2019_sample_eval.py`
  - streams the local BPI CSV
  - selects a balanced sample across four P2P categories
  - converts event-log rows into read-only ERP approval evidence records
  - runs the current evidence-first case review pipeline
  - compares it with a strict P2P rule baseline
  - scores every case with an independent reviewer rubric

- `backend/tests/test_erp_approval_bpi2019_sample_eval.py`
  - verifies sample selection, evidence-record construction, invoice-before-GR detection, false-approve scoring, and the current-agent evaluation wrapper without the large CSV.

- `backend/benchmarks/cases/erp_approval/bpi2019_sample_cases.json`
  - compact derived 300-case sample evidence set.
  - this is not the raw dataset.

- `reports/evaluations/bpi2019_evidence_sample_eval_latest.md`
- `reports/evaluations/bpi2019_evidence_sample_eval_latest.json`
  - latest generated evaluation output.

## How To Re-run

From repo root:

```powershell
backend\.venv\Scripts\python.exe -m backend.benchmarks.erp_approval_bpi2019_sample_eval `
  --csv artifacts\downloads\bpi2019\csv\BPI_Challenge_2019.csv `
  --limit 300 `
  --report reports\evaluations\bpi2019_evidence_sample_eval_latest.md `
  --json reports\evaluations\bpi2019_evidence_sample_eval_latest.json `
  --cases-out backend\benchmarks\cases\erp_approval\bpi2019_sample_cases.json
```

## Latest Result

- Cases evaluated: 300
- Category mix: 75 each for:
  - 3-way match, invoice after GR
  - 3-way match, invoice before GR
  - 2-way match
  - Consignment
- Average score: 92.53
- False approve count: 0
- Critical failures: 0
- Major failures: 65
- Current agent status distribution: 300 `escalate`

## What The Strict Reviewer Found

The current agent is safe on the most important boundary: it did not recommend approval from BPI event-log evidence alone.

The main weakness is not safety but maturity:

- BPI P2P-specific process semantics are not first-class yet.
- The agent often treats PO/GR/invoice rows as generic evidence instead of explicitly explaining 3-way, 2-way, or consignment flow.
- Sequence reasoning is thin for invoice-before-GR, historical Clear Invoice, reversals/cancellations, and payment block events.
- Amount reasoning is thin for cumulative net-worth variation and partial/repeated invoice patterns.
- BPI 2019 does not include the approval workflow itself, so it should support a dossier but cannot by itself prove an approval can pass.

## Recommended Next Product Fix

Add a dedicated P2P process-evidence reviewer role:

```text
BPI/event-log evidence
-> p2p_process_fact_extractor
-> match_type_classifier
-> sequence_anomaly_reviewer
-> amount_consistency_reviewer
-> process_evidence_patch_validator
-> case_state / dossier update
```

The model can judge process meaning, but it must still output a structured patch that deterministic validators check before writing to the case.

## Boundary

No ERP write action was executed.
