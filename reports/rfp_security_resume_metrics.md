# RFP Security Resume Metrics

## Headline Metrics

These are the strongest metrics to quote for this standalone repository:

1. `20-case RFP/security benchmark: 100% pass rate`
   - Why it matters: shows the domain pack, retrieval strategy, and answer-governance path run end to end as a production-shaped capability.

2. `Retrieval hit@k: 100%, retrieval recall@k: 97.22%`
   - Why it matters: the baseline hybrid retrieval path is not just pluggable; it is also measurably strong on the shipped evaluation set.

3. `Groundedness: 0.75, response completeness: 0.875`
   - Why it matters: the answer path improved auditability and completeness together, not one at the expense of the other.

4. `Citation precision: 44.78%, citation recall: 88.89%`
   - Why it matters: citation pruning materially reduced weak evidence spray while preserving broad coverage of required support.

5. `Unsupported claim rate: 0%`
   - Why it matters: this is the safety guardrail that matters most in security questionnaire automation.

6. `Pressure matrix: concurrency 1/2/4/8, 0% error rate, p95 latency 19.59s`
   - Why it matters: the path was exercised under load rather than only in happy-path smoke mode.

7. `Live validation smoke: 3/3 passed with trace completeness, SSE order, and session integrity at 100%`
   - Why it matters: the RFP/security specialization did not break the existing runtime chain.

## Resume Bullet

- Built a standalone RFP/security questionnaire drafting platform on top of a local-first agent runtime, adding a pluggable hybrid-RAG retrieval layer, evidence-planning answer governance, and a 20-case benchmark suite that reached 100% pass rate, 97.22% retrieval recall@k, 0% unsupported claims, and clean live-validation plus concurrency pressure runs.

## README-Ready Headline Options

- `RFP/security benchmark: 20 cases, 100% pass, 97.22% retrieval recall@k, 0% unsupported claims`
- `Evidence-governed security-answer generation: groundedness 0.75, completeness 0.875, citation precision 44.78%`
- `Pressure-tested hybrid RAG: concurrency 1/2/4/8, error rate 0%, live validation smoke 3/3 passed`
