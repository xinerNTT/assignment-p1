"""
Test suite for loan_calc.calculator.

Covers normal usage plus the edge cases called out in the assignment:
- 0% interest loans
- 1-month tenure
- very large principal amounts
- prepayment amounts larger than the outstanding balance

Also documents (via explicit assertions / comments) two known quirks of the
current implementation described in ARCHITECTURE.md:
  1. amortisation_schedule() has an off-by-one bug: it returns
     `tenure_months - 1` rows instead of `tenure_months` rows
     (range(1, tenure_months) never reaches `tenure_months`).
  2. remaining_tenure() treats `annual_rate / 100` as a periodic rate
     (not divided by 12 like `_monthly_rate`), which is an inconsistency
     worth being aware of when reasoning about prepayment_savings().
"""
import csv
import math

import pytest

from loan_calc import (
    emi,
    total_payment,
    total_interest,
    amortisation_schedule,
    outstanding_after,
    remaining_tenure,
    prepayment_savings,
    compare_offers,
    eligible_amount,
    format_inr,
    schedule_to_csv,
    summary,
)


# ---------------------------------------------------------------------------
# emi()
# ---------------------------------------------------------------------------

class TestEmi:
    def test_basic_emi(self):
        # Standard loan: principal=500000, rate=9.5%, tenure=36 months
        result = emi(500000, 9.5, 36)
        assert result == pytest.approx(16016.96, abs=0.5)
        assert result > 0

    def test_zero_interest_rate(self):
        # Edge case: 0% interest -> straight-line division, no interest component
        result = emi(120000, 0, 12)
        assert result == pytest.approx(10000.0)

    def test_zero_interest_with_remainder(self):
        # 0% interest where division doesn't divide evenly
        result = emi(100000, 0, 3)
        assert result == pytest.approx(33333.33, abs=0.01)

    def test_one_month_tenure(self):
        # Edge case: 1-month tenure -> single payment covering principal + 1 month interest
        result = emi(100000, 9, 1)
        assert result == pytest.approx(100750.0, abs=0.01)

    def test_one_month_tenure_zero_interest(self):
        # 1-month tenure combined with 0% interest -> emi equals full principal
        result = emi(50000, 0, 1)
        assert result == pytest.approx(50000.0)

    def test_very_large_principal(self):
        # Edge case: very large principal should not overflow or error
        principal = 10 ** 12  # 1 trillion
        result = emi(principal, 8.5, 240)
        assert result > 0
        assert math.isfinite(result)
        # Sanity: total repaid must exceed the principal for a nonzero rate
        assert result * 240 > principal

    def test_very_large_principal_zero_interest(self):
        principal = 10 ** 12
        result = emi(principal, 0, 240)
        assert result == pytest.approx(principal / 240, rel=1e-9)

    def test_negative_principal_raises(self):
        with pytest.raises(ValueError):
            emi(-1000, 9.5, 12)

    def test_zero_principal_raises(self):
        with pytest.raises(ValueError):
            emi(0, 9.5, 12)

    def test_negative_tenure_raises(self):
        with pytest.raises(ValueError):
            emi(100000, 9.5, -5)

    def test_zero_tenure_raises(self):
        with pytest.raises(ValueError):
            emi(100000, 9.5, 0)


# ---------------------------------------------------------------------------
# total_payment() / total_interest()
# ---------------------------------------------------------------------------

class TestTotalPaymentAndInterest:
    def test_total_payment_basic(self):
        principal, rate, tenure = 500000, 9.5, 36
        tp = total_payment(principal, rate, tenure)
        assert tp == pytest.approx(emi(principal, rate, tenure) * tenure, abs=0.01)

    def test_total_payment_zero_interest(self):
        # With 0% interest, total payment should equal the principal exactly
        tp = total_payment(120000, 0, 12)
        assert tp == pytest.approx(120000.0)

    def test_total_interest_zero_interest(self):
        # With 0% interest, total interest paid should be (near) zero
        ti = total_interest(120000, 0, 12)
        assert ti == pytest.approx(0.0, abs=0.01)

    def test_total_interest_positive_for_nonzero_rate(self):
        ti = total_interest(500000, 9.5, 36)
        assert ti > 0

    def test_total_payment_one_month_tenure(self):
        tp = total_payment(100000, 9, 1)
        # Only one instalment is paid
        assert tp == pytest.approx(emi(100000, 9, 1))

    def test_total_payment_very_large_principal(self):
        principal = 10 ** 12
        tp = total_payment(principal, 9.5, 36)
        assert tp > principal
        assert math.isfinite(tp)


# ---------------------------------------------------------------------------
# amortisation_schedule()
# ---------------------------------------------------------------------------

class TestAmortisationSchedule:
    def test_schedule_row_count_has_off_by_one_bug(self):
        # Documents the known off-by-one bug: range(1, tenure_months) means
        # the schedule has tenure_months - 1 rows, not tenure_months rows.
        tenure = 12
        sched = amortisation_schedule(100000, 9.5, tenure)
        assert len(sched) == tenure - 1

    def test_schedule_fields_present(self):
        sched = amortisation_schedule(100000, 9.5, 12)
        row = sched[0]
        assert set(row.keys()) == {"month", "emi", "interest", "principal", "balance"}
        assert row["month"] == 1

    def test_schedule_balance_decreases_monotonically(self):
        sched = amortisation_schedule(100000, 9.5, 24)
        balances = [row["balance"] for row in sched]
        for earlier, later in zip(balances, balances[1:]):
            assert later <= earlier

    def test_schedule_zero_interest(self):
        # With 0% interest every month's interest component should be 0
        sched = amortisation_schedule(120000, 0, 12)
        for row in sched:
            assert row["interest"] == 0

    def test_schedule_one_month_tenure_returns_empty(self):
        # With tenure_months=1, range(1, 1) is empty -> schedule has 0 rows.
        # This is an edge case worth being explicit about given the off-by-one bug.
        sched = amortisation_schedule(100000, 9, 1)
        assert sched == []

    def test_schedule_very_large_principal(self):
        principal = 10 ** 12
        sched = amortisation_schedule(principal, 8.5, 24)
        assert len(sched) == 23
        assert all(math.isfinite(row["balance"]) for row in sched)
        assert all(row["balance"] >= 0 for row in sched)


# ---------------------------------------------------------------------------
# outstanding_after()
# ---------------------------------------------------------------------------

class TestOutstandingAfter:
    def test_no_payments_made_returns_full_principal(self):
        result = outstanding_after(500000, 9.5, 36, 0)
        assert result == pytest.approx(500000.0)

    def test_negative_months_paid_returns_full_principal(self):
        result = outstanding_after(500000, 9.5, 36, -3)
        assert result == pytest.approx(500000.0)

    def test_outstanding_after_matches_schedule(self):
        principal, rate, tenure = 500000, 9.5, 36
        sched = amortisation_schedule(principal, rate, tenure)
        result = outstanding_after(principal, rate, tenure, 5)
        assert result == sched[4]["balance"]

    def test_outstanding_after_exceeds_schedule_length_returns_zero(self):
        # Given the off-by-one bug, schedule has tenure_months - 1 rows,
        # so requesting months_paid >= tenure_months - 1 should return 0.0
        result = outstanding_after(100000, 9.5, 12, 50)
        assert result == 0.0

    def test_outstanding_after_zero_interest(self):
        result = outstanding_after(120000, 0, 12, 6)
        assert result == pytest.approx(60000.0, abs=1.0)

    def test_outstanding_after_very_large_principal(self):
        principal = 10 ** 12
        result = outstanding_after(principal, 8.5, 240, 12)
        assert result < principal
        assert result > 0


# ---------------------------------------------------------------------------
# remaining_tenure()
# ---------------------------------------------------------------------------

class TestRemainingTenure:
    def test_zero_balance_returns_zero(self):
        assert remaining_tenure(0, 9.5, 5000) == 0

    def test_negative_balance_returns_zero(self):
        assert remaining_tenure(-100, 9.5, 5000) == 0

    def test_zero_interest_straight_line(self):
        # balance=100000, instalment=10000, 0% interest -> exactly 10 months
        result = remaining_tenure(100000, 0, 10000)
        assert result == 10

    def test_zero_interest_rounds_up(self):
        # balance doesn't divide evenly -> ceil to next whole month
        result = remaining_tenure(100000, 0, 30000)
        assert result == 4  # 100000 / 30000 = 3.33... -> ceil = 4

    def test_instalment_too_small_raises(self):
        # Instalment doesn't even cover first month's interest
        with pytest.raises(ValueError):
            remaining_tenure(100000, 50, 100)  # 50% rate used directly as periodic rate

    def test_standard_case_returns_positive_int(self):
        result = remaining_tenure(100000, 9.5, 5000)
        assert isinstance(result, int)
        assert result > 0

    def test_very_large_balance(self):
        balance = 10 ** 12
        instalment = 10 ** 10
        result = remaining_tenure(balance, 9.5, instalment)
        assert result > 0
        assert math.isfinite(result)


# ---------------------------------------------------------------------------
# prepayment_savings()
# ---------------------------------------------------------------------------

class TestPrepaymentSavings:
    def test_basic_prepayment(self):
        result = prepayment_savings(500000, 9.5, 36, 12, 50000)
        assert "emi" in result
        assert "months_saved" in result
        assert "new_tenure" in result
        assert "interest_saved" in result
        assert "interest_paid_before_prepayment" in result
        assert result["months_saved"] >= 0

    def test_prepayment_amount_larger_than_balance_fully_closes_loan(self):
        # Edge case: prepay_amount exceeds the outstanding balance at that
        # month, so the loan should close immediately (months_left = 0).
        principal, rate, tenure, prepay_month = 100000, 9.5, 24, 6
        sched = amortisation_schedule(principal, rate, tenure)
        balance_at_month = sched[prepay_month - 1]["balance"]
        huge_prepayment = balance_at_month + 1_000_000  # Far exceeds balance

        result = prepayment_savings(principal, rate, tenure, prepay_month, huge_prepayment)

        # months_left should be 0, so new_tenure == prepay_month
        assert result["new_tenure"] == prepay_month
        # Interest saved should be close to (or more than) the full remaining interest
        assert result["interest_saved"] > 0

    def test_prepayment_exactly_equal_to_balance_closes_loan(self):
        principal, rate, tenure, prepay_month = 100000, 9.5, 24, 6
        sched = amortisation_schedule(principal, rate, tenure)
        balance_at_month = sched[prepay_month - 1]["balance"]

        result = prepayment_savings(principal, rate, tenure, prepay_month, balance_at_month)

        assert result["new_tenure"] == prepay_month

    def test_prepayment_zero_interest_loan(self):
        # 0% interest loan with a mid-tenure prepayment
        result = prepayment_savings(120000, 0, 12, 6, 20000)
        assert result["months_saved"] >= 0
        assert result["interest_saved"] == pytest.approx(0.0, abs=0.01)

    def test_small_prepayment_reduces_tenure_or_keeps_same(self):
        result = prepayment_savings(500000, 9.5, 36, 12, 1000)
        # A tiny prepayment should save zero or a small number of months
        assert result["months_saved"] >= 0

    def test_prepayment_very_large_principal(self):
        principal = 10 ** 12
        result = prepayment_savings(principal, 8.5, 240, 60, 10 ** 10)
        assert result["interest_saved"] >= 0
        assert math.isfinite(result["interest_saved"])


# ---------------------------------------------------------------------------
# compare_offers()
# ---------------------------------------------------------------------------

class TestCompareOffers:
    def test_offers_sorted_by_total_cost_ascending(self):
        offers = [
            {"bank": "BankA", "rate": 9.5, "tenure": 36, "processing_fee_pct": 1.0},
            {"bank": "BankB", "rate": 8.5, "tenure": 36},
            {"bank": "BankC", "rate": 10.0, "tenure": 36, "processing_fee_pct": 0.5},
        ]
        result = compare_offers(500000, offers)
        costs = [r["total_cost"] for r in result]
        assert costs == sorted(costs)

    def test_offer_without_processing_fee_defaults_to_zero(self):
        offers = [{"bank": "BankX", "rate": 9.0, "tenure": 24}]
        result = compare_offers(100000, offers)
        assert result[0]["processing_fee"] == 0

    def test_offer_fields_present(self):
        offers = [{"bank": "BankY", "rate": 9.0, "tenure": 12, "processing_fee_pct": 2.0}]
        result = compare_offers(200000, offers)
        row = result[0]
        assert set(row.keys()) == {"bank", "emi", "total_interest", "processing_fee", "total_cost"}

    def test_empty_offers_list_returns_empty(self):
        result = compare_offers(100000, [])
        assert result == []

    def test_offers_zero_interest(self):
        offers = [{"bank": "ZeroBank", "rate": 0, "tenure": 12}]
        result = compare_offers(120000, offers)
        assert result[0]["total_interest"] == pytest.approx(0.0, abs=0.01)

    def test_offers_very_large_principal(self):
        principal = 10 ** 12
        offers = [
            {"bank": "BigBank", "rate": 8.0, "tenure": 240, "processing_fee_pct": 0.5},
        ]
        result = compare_offers(principal, offers)
        assert result[0]["total_cost"] > 0
        assert math.isfinite(result[0]["total_cost"])


# ---------------------------------------------------------------------------
# eligible_amount()
# ---------------------------------------------------------------------------

class TestEligibleAmount:
    def test_basic_eligibility(self):
        result = eligible_amount(100000, 20000, 9.5, 60)
        assert result > 0

    def test_insufficient_income_returns_zero(self):
        # existing_emis exceeds the FOIR-capped available budget
        result = eligible_amount(50000, 40000, 9.5, 60, foir=0.5)
        assert result == 0.0

    def test_exactly_zero_available_returns_zero(self):
        # available == 0 exactly -> should return 0.0 (available <= 0 check)
        result = eligible_amount(40000, 20000, 9.5, 60, foir=0.5)
        assert result == 0.0

    def test_zero_interest_rate(self):
        # 0% interest -> straight-line available * tenure_months
        result = eligible_amount(100000, 0, 0, 24, foir=0.5)
        assert result == pytest.approx(50000 * 24, rel=1e-6)

    def test_default_foir_is_half(self):
        # foir defaults to 0.5
        result_default = eligible_amount(100000, 0, 9.5, 60)
        result_explicit = eligible_amount(100000, 0, 9.5, 60, foir=0.5)
        assert result_default == result_explicit

    def test_very_large_income(self):
        income = 10 ** 9
        result = eligible_amount(income, 0, 9.5, 240)
        assert result > 0
        assert math.isfinite(result)


# ---------------------------------------------------------------------------
# format_inr()
# ---------------------------------------------------------------------------

class TestFormatInr:
    def test_small_amount(self):
        assert format_inr(500) == "₹500.00"

    def test_thousands_grouping(self):
        assert format_inr(12345.67) == "₹12,345.67"

    def test_lakhs_grouping(self):
        assert format_inr(1234567.5) == "₹12,34,567.50"

    def test_negative_amount(self):
        assert format_inr(-100000) == "-₹1,00,000.00"

    def test_zero_amount(self):
        assert format_inr(0) == "₹0.00"

    def test_very_large_amount_crores(self):
        # 1,000,000,000 (1 billion) -> crores-style grouping
        result = format_inr(1_000_000_000)
        assert result.startswith("₹")
        assert "," in result
        # Should not raise and should be a well-formed string ending in .00
        assert result.endswith(".00")

    def test_rounding_behavior(self):
        # Ensure amount is rounded to 2 decimals before formatting
        assert format_inr(100.005) in ("₹100.00", "₹100.01")


# ---------------------------------------------------------------------------
# schedule_to_csv()
# ---------------------------------------------------------------------------

class TestScheduleToCsv:
    def test_writes_header_and_rows(self, tmp_path):
        sched = amortisation_schedule(100000, 9.5, 12)
        out_file = tmp_path / "schedule.csv"
        schedule_to_csv(sched, str(out_file))

        assert out_file.exists()
        with open(out_file, newline="") as fh:
            reader = csv.reader(fh)
            rows = list(reader)

        assert rows[0] == ["month", "emi", "interest", "principal", "balance"]
        # Number of data rows should match schedule length
        assert len(rows) - 1 == len(sched)

    def test_empty_schedule_still_writes_header(self, tmp_path):
        # Edge case: 1-month tenure produces an empty schedule due to the
        # off-by-one bug; CSV should still contain just the header.
        sched = amortisation_schedule(100000, 9, 1)
        out_file = tmp_path / "empty_schedule.csv"
        schedule_to_csv(sched, str(out_file))

        with open(out_file, newline="") as fh:
            reader = csv.reader(fh)
            rows = list(reader)

        assert rows == [["month", "emi", "interest", "principal", "balance"]]

    def test_overwrites_existing_file(self, tmp_path):
        out_file = tmp_path / "schedule.csv"
        out_file.write_text("old content")

        sched = amortisation_schedule(100000, 9.5, 12)
        schedule_to_csv(sched, str(out_file))

        content = out_file.read_text()
        assert "old content" not in content
        assert "month,emi,interest,principal,balance" in content


# ---------------------------------------------------------------------------
# summary()
# ---------------------------------------------------------------------------

class TestSummary:
    def test_summary_contains_expected_keys(self):
        result = summary(500000, 9.5, 36)
        expected_keys = {
            "principal", "rate", "tenure", "emi",
            "total_interest", "total_payment", "last_emi", "currency",
        }
        assert set(result.keys()) == expected_keys

    def test_summary_currency_is_inr(self):
        result = summary(100000, 9.5, 12)
        assert result["currency"] == "INR"

    def test_summary_rate_formatting(self):
        result = summary(100000, 9.5, 12)
        assert result["rate"] == "9.5% p.a."

    def test_summary_tenure_formatting(self):
        result = summary(100000, 9.5, 12)
        assert result["tenure"] == "12 months"

    def test_summary_last_emi_date_rollover(self):
        from datetime import date
        # Starting Nov 2023, 3-month tenure -> last EMI should be Jan 2024
        result = summary(100000, 9.5, 3, start=date(2023, 11, 1))
        assert result["last_emi"] == "2024-02"

    def test_summary_zero_interest(self):
        result = summary(120000, 0, 12)
        assert result["total_interest"] == "₹0.00"

    def test_summary_one_month_tenure(self):
        from datetime import date
        result = summary(100000, 9, 1, start=date(2024, 1, 1))
        assert result["tenure"] == "1 months"
        assert result["last_emi"] == "2024-02"

    def test_summary_very_large_principal(self):
        result = summary(10 ** 12, 8.5, 240)
        assert result["currency"] == "INR"
        assert result["principal"].startswith("₹")

    def test_summary_default_start_is_today(self):
        from datetime import date
        result = summary(100000, 9.5, 12)
        today = date.today()
        expected_end_year = today.year + (today.month - 1 + 12) // 12
        expected_end_month = (today.month - 1 + 12) % 12 + 1
        assert result["last_emi"] == f"{expected_end_year}-{expected_end_month:02d}"
