# ERP Approval Policy Matrix (Fictional Local Policy)

This is fictional local policy evidence for the ERP Approval Agent Workbench. It is not production ERP policy and does not authorize any ERP write action.

## Procurement PR-CTRL-001: Purchase Requisition Evidence

Before a purchase requisition can receive a pass-style reviewer memo, the case must include a traceable approval request, requester identity, department, cost center, line items, amount, currency, vendor, and business purpose. A user statement alone cannot satisfy this requirement.

Acceptable evidence: ERP approval request export, purchase requisition record, signed intake form, or local attachment with source id and concrete fields.

Unacceptable evidence: "my manager approved it", "please pass PR-1001", or free text without requester, amount, vendor, and cost center.

## Procurement PR-CTRL-002: Budget Availability

Purchase requisitions must include budget availability or budget reservation evidence for the relevant cost center. The evidence must show available budget, requested amount, currency, and budget owner or source system.

Acceptable evidence: budget record, budget reservation, finance approval note with source id, or cost-center budget report.

Unacceptable evidence: verbal statements that budget is enough, screenshots without cost center or amount, or evidence with conflicting currency.

## Procurement PR-CTRL-003: Vendor Onboarding and Supplier Risk

The supplier must have onboarding status and risk status evidence before a pass-style recommendation can be considered. Supplier risk evidence includes sanctions, block status, or due diligence result.

Acceptable evidence: vendor master record, supplier onboarding approval, sanctions screening result, risk review record.

Unacceptable evidence: supplier name only, sales email, or a quote without supplier master status.

## Procurement PR-CTRL-004: Quote, Contract, or Price Basis

Purchase requisitions must include quote, comparison, contract, framework agreement, or approved price basis evidence. The evidence must tie the vendor and amount to the requested purchase.

Acceptable evidence: quote, bid comparison, contract price schedule, framework agreement, or procurement exception note.

Unacceptable evidence: "vendor quoted us before", old pricing with no date, or a quote that names a different vendor or amount.

## Procurement PR-CTRL-005: Approval Matrix and Threshold

The case must include approval matrix or threshold policy evidence showing required reviewers for the amount, department, cost center, and risk level.

Acceptable evidence: approval matrix excerpt, threshold policy, workflow routing policy, or role-based approval rule.

Unacceptable evidence: assuming a manager can approve without threshold evidence.

## Invoice PAY-CTRL-001: Three-Way Match

Invoice payment review requires invoice, purchase order, goods receipt, vendor record, payment terms, duplicate payment check, and approval matrix evidence. PO, GRN, and invoice must be consistent or conflicts must be escalated.

Acceptable evidence: invoice record, PO record, GRN record, three-way match report, duplicate payment check, payment terms.

Unacceptable evidence: invoice number only, payment request without PO/GRN, or a Clear Invoice event treated as current payment authorization.

## Supplier VEND-CTRL-001: Supplier Onboarding

Supplier onboarding requires vendor profile, tax information, bank information, sanctions screening, beneficial owner check, procurement due diligence, and contract/NDA/DPA evidence where applicable.

Acceptable evidence: vendor profile, bank verification, tax record, sanctions check, due diligence checklist, legal document.

Unacceptable evidence: business card, supplier website, or user statement that the supplier is safe.

## Contract LEGAL-CTRL-001: Contract Exception Review

Contract exceptions require contract text, redline or exception clause, standard terms, legal policy, liability clause review, payment terms review, termination clause review, and legal reviewer assignment.

Acceptable evidence: contract draft, redline, legal exception memo, legal policy excerpt, reviewer assignment.

Unacceptable evidence: user saying legal is fine without a legal record.

## Budget FIN-CTRL-001: Budget Exception

Budget exceptions require budget record, budget owner, available budget, exception reason, finance policy, and finance approval matrix. Insufficient budget must be escalated or blocked until finance review is provided.

Acceptable evidence: finance review, budget owner approval, exception request, budget report.

Unacceptable evidence: verbal promise to replenish budget later.
