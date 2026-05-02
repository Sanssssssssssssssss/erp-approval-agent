from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.benchmarks.erp_approval_bpi2019_sample_eval import (  # noqa: E402
    CSV_FIELDS,
    build_bpi_sample_case,
    derive_bpi_case_facts,
    evaluate_bpi_case,
    load_bpi_case_groups,
    run_bpi_rule_baseline,
    run_current_agent,
    score_agent_against_bpi,
    select_bpi_case_ids,
)


class Bpi2019SampleEvalTests(unittest.TestCase):
    def test_selects_balanced_case_ids_and_builds_evidence_records(self) -> None:
        with tempfile.TemporaryDirectory(prefix="bpi2019-test-") as workspace:
            csv_path = Path(workspace) / "bpi.csv"
            _write_fixture_csv(csv_path)

            selected = select_bpi_case_ids(csv_path, limit=4)
            groups = load_bpi_case_groups(csv_path, selected)
            cases = [build_bpi_sample_case(case_id, groups[case_id]) for case_id in selected]

            self.assertEqual(len(cases), 4)
            match_types = {case["bpi_facts"]["match_type"] for case in cases}
            self.assertIn("three_way_invoice_after_gr", match_types)
            self.assertIn("three_way_invoice_before_gr", match_types)
            self.assertIn("two_way", match_types)
            self.assertIn("consignment", match_types)
            first_records = cases[0]["provided_context_records"]
            self.assertTrue(all(record["source_id"] and record["title"] and record["record_type"] and record["content"] for record in first_records))

    def test_current_agent_does_not_approve_from_bpi_event_log_only(self) -> None:
        rows = _fixture_rows_for_case("4507000001_00010", "3-way match, invoice after GR")
        case = build_bpi_sample_case("4507000001_00010", rows)

        observed = run_current_agent(case)

        self.assertNotEqual(observed["recommendation"]["status"], "recommend_approve")
        self.assertIn("No ERP write action was executed", observed["non_action_statement"])
        self.assertIn("purchase_order_present", observed["claim_types"])
        self.assertIn("invoice_present", observed["claim_types"])
        self.assertIn("goods_receipt_present", observed["claim_types"])

    def test_strict_scorer_flags_false_approve_as_critical(self) -> None:
        rows = _fixture_rows_for_case("4507000002_00010", "3-way match, invoice after GR", include_gr=False)
        case = build_bpi_sample_case("4507000002_00010", rows)
        observed = run_current_agent(case)
        observed["recommendation"]["status"] = "recommend_approve"
        baseline = run_bpi_rule_baseline(case)

        score = score_agent_against_bpi(case, observed, baseline)

        self.assertEqual(score["severity"], "critical")
        self.assertLessEqual(score["score"], 49)

    def test_invoice_before_gr_is_identified_as_risk(self) -> None:
        rows = _fixture_rows_for_case("4507000003_00010", "3-way match, invoice before GR", invoice_before_gr=True)

        facts = derive_bpi_case_facts("4507000003_00010", rows)

        self.assertTrue(facts.invoice_before_goods_receipt)
        self.assertIn("invoice_before_goods_receipt", facts.known_risks)

    def test_evaluate_case_returns_rule_baseline_and_agent_score(self) -> None:
        rows = _fixture_rows_for_case("4507000004_00010", "2-way match", include_gr=False)
        case = build_bpi_sample_case("4507000004_00010", rows)

        result = evaluate_bpi_case(case)

        self.assertIn("current_agent", result)
        self.assertIn("rule_baseline", result)
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 100)


def _write_fixture_csv(path: Path) -> None:
    rows = []
    rows.extend(_fixture_rows_for_case("4507000001_00010", "3-way match, invoice after GR"))
    rows.extend(_fixture_rows_for_case("4507000002_00010", "3-way match, invoice before GR", invoice_before_gr=True))
    rows.extend(_fixture_rows_for_case("4507000003_00010", "2-way match", include_gr=False))
    rows.extend(_fixture_rows_for_case("4507000004_00010", "Consignment", include_invoice=False))
    with path.open("w", newline="", encoding="latin-1") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _fixture_rows_for_case(
    case_id: str,
    item_category: str,
    *,
    include_gr: bool = True,
    include_invoice: bool = True,
    invoice_before_gr: bool = False,
) -> list[dict[str, str]]:
    po, item = case_id.split("_", 1)
    base = {
        "case Spend area text": "Operations",
        "case Company": "companyID_TEST",
        "case Document Type": "Standard PO",
        "case Sub spend area text": "IT equipment",
        "case Purchasing Document": po,
        "case Purch. Doc. Category name": "Purchase order",
        "case Vendor": "vendor_TEST",
        "case Item Type": "Standard",
        "case Item Category": item_category,
        "case Spend classification text": "Indirect spend",
        "case Source": "source_TEST",
        "case Name": "Vendor Test",
        "case GR-Based Inv. Verif.": "true" if "3-way" in item_category and "before" not in item_category.lower() else "false",
        "case Item": item,
        "case concept:name": case_id,
        "case Goods Receipt": "true" if include_gr else "false",
        "event User": "NONE",
        "event org:resource": "NONE",
    }
    events: list[tuple[str, str, str]] = [("1", "Create Purchase Order Item", "01-01-2018 08:00:00.000")]
    if include_invoice and invoice_before_gr:
        events.append(("2", "Vendor creates invoice", "02-01-2018 08:00:00.000"))
    if include_gr:
        events.append(("3", "Record Goods Receipt", "03-01-2018 08:00:00.000"))
    if include_invoice and not invoice_before_gr:
        events.append(("4", "Vendor creates invoice", "04-01-2018 08:00:00.000"))
    if include_invoice:
        events.append(("5", "Record Invoice Receipt", "05-01-2018 08:00:00.000"))
        events.append(("6", "Clear Invoice", "06-01-2018 08:00:00.000"))
    rows = []
    for event_id, activity, timestamp in events:
        row = dict(base)
        row["eventID"] = f"{case_id}-{event_id}"
        row["event concept:name"] = activity
        row["event Cumulative net worth (EUR)"] = "100.0"
        row["event time:timestamp"] = timestamp
        rows.append(row)
    return rows


if __name__ == "__main__":
    unittest.main()
