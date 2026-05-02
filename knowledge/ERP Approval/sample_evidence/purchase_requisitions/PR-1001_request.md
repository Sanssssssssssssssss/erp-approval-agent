# PR-1001 Purchase Requisition Form

- Approval ID: PR-1001
- Requester: Lin Chen
- Department: Operations
- Cost center: OPS-CC-10
- Vendor: Acme Supplies
- Amount: USD 24,500
- Purpose: Replacement laptops for the Operations team

Line items:

| Item | Qty | Unit Price | Total |
| --- | ---: | ---: | ---: |
| Laptop, 14 inch business model | 10 | USD 2,250 | USD 22,500 |
| Docking station | 10 | USD 200 | USD 2,000 |

Control notes:

- Mock split-order check: passed; no related PR for the same vendor and cost center was found in the local fixture window.
- Quote evidence is intentionally missing for PR-1001, so this case should not become `recommend_approve`.

