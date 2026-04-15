# RFP Security Quality Delta

## Baseline Vs Tuned

The standalone project preserves both the baseline and the tuned reference numbers so future changes have a stable comparison point.

| Metric | Baseline | Tuned | Delta |
| --- | ---: | ---: | ---: |
| overall_pass_rate | `0.9500` | `1.0000` | `+0.0500` |
| retrieval_hit_at_k | `0.9444` | `1.0000` | `+0.0556` |
| retrieval_recall_at_k | `0.7963` | `0.9722` | `+0.1759` |
| evidence_coverage | `0.7778` | `0.8889` | `+0.1111` |
| citation_precision | `0.1271` | `0.4478` | `+0.3207` |
| citation_recall | `0.7778` | `0.8889` | `+0.1111` |
| groundedness | `0.4092` | `0.7500` | `+0.3408` |
| response_completeness | `0.4292` | `0.8750` | `+0.4458` |
| relevance | `0.7797` | `0.9558` | `+0.1761` |
| unsupported_claim_rate | `0.0000` | `0.0000` | `+0.0000` |

## Pressure-Matrix Delta

| Metric | Baseline | Tuned | Delta |
| --- | ---: | ---: | ---: |
| pass_rate | `1.0000` | `1.0000` | `+0.0000` |
| error_rate | `0.0000` | `0.0000` | `+0.0000` |
| latency_ms_p50 | `3514.5` | `8122.5` | `+4608.0` |
| latency_ms_p95 | `22408.1` | `19592.1` | `-2816.0` |
| retrieval_recall_at_k | `0.8854` | `1.0000` | `+0.1146` |
| citation_precision | `0.2005` | `0.3289` | `+0.1284` |
| citation_recall | `0.8750` | `0.7500` | `-0.1250` |
| groundedness | `0.4437` | `0.8875` | `+0.4438` |
| response_completeness | `0.4750` | `1.0000` | `+0.5250` |
| unsupported_claim_rate | `0.0000` | `0.0000` | `+0.0000` |

## Interpretation

- The tuned branch stopped treating retrieved evidence as automatically citable evidence.
- It replaced phrase-equality support checks with evidence-point mapping and authoritative evidence preference.
- It enriched the query fed into retrieval without changing the retrieval strategy interface.
- It preserved `unsupported_claim_rate = 0.0`.

## Tradeoff

- The tuned branch is slower on pressure-matrix p50 latency because the planning pool is richer and the verifier path is stricter.
- That tradeoff did not show up as instability: pass rate, error rate, and live validation stayed clean.

## Conclusion

The tuned path is worth keeping as the repository default because the quality gains come from stronger evidence mapping and citation governance, not evaluator trickery.
