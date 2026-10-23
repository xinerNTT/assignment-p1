# Architecture — `loan_calc` package

This document describes the internal architecture of the `loan_calc` package and explains, in detail, what every function does, how data flows between them, and how the package is consumed by the CLI (`cli.py`).

## 1. Package layout

```
loan-calc/loan-calc/
├── cli.py                  # Command-line entry point, thin wrapper around the package
├── loan_calc/
│   ├── __init__.py         # Re-exports the public API of calculator.py
│   └── calculator.py       # All business logic (pure functions, no I/O except schedule_to_csv)
└── tests/                  # (currently empty, placeholder for unit tests)
```

The package follows a simple **flat module** design: a single module (`calculator.py`) contains all domain logic, grouped by responsibility (core EMI math → schedule generation → prepayment/eligibility analysis → formatting/reporting). There is no class hierarchy — every unit of logic is a standalone, mostly-pure function that takes primitive arguments (numbers, dicts, lists) and returns primitive results. This makes the module easy to test, easy to reason about, and easy to compose.

## 2. `__init__.py`

```python
from .calculator import *  # noqa
```

- Purpose: Acts as the public façade of the package. Every name defined in `calculator.py` (that doesn't start with an underscore, since there is no `__all__` defined) becomes importable directly from `loan_calc`, e.g. `from loan_calc import emi` instead of `from loan_calc.calculator import emi`.
- This is why `cli.py` can do `from loan_calc import amortisation_schedule, prepayment_savings, summary` — these functions are "promoted" to the package root by this wildcard import.
- The private helper `_monthly_rate` (leading underscore) is *not* re-exported by the wildcard import convention, keeping it as an internal implementation detail.

## 3. `calculator.py` — function-by-function breakdown

### Module-level constant

- **`DEFAULT_CURRENCY = "INR"`** — A fixed string used later by `summary()` to tag the currency of the computed figures. The package is hard-coded for Indian Rupee calculations (see also `format_inr`).

---

### `_monthly_rate(annual_rate)`

```python
def _monthly_rate(annual_rate):
    r = round(annual_rate / 1200, 4)
    return r
```

- **Role:** Private helper that converts an annual interest rate expressed as a percentage (e.g. `9.5` meaning 9.5% p.a.) into a monthly *decimal* interest rate.
- **Math:** Dividing by `1200` is equivalent to `(annual_rate / 100) / 12` — first converting percent to a fraction, then converting annual to monthly.
- Rounded to 4 decimal places to avoid floating-point drift accumulating across amortisation calculations.
- Used by `emi()` and `eligible_amount()`.

---

### `emi(principal, annual_rate, tenure_months)`

- **Role:** Computes the **Equated Monthly Instalment** — the fixed monthly payment required to fully amortise a loan.
- **Validation:** Raises `ValueError` if `tenure_months <= 0` or `principal <= 0`.
- **Math:**
  - Computes the monthly rate `r` via `_monthly_rate`.
  - **Zero-interest special case:** if `r == 0`, the EMI is simply `principal / tenure_months` (straight-line repayment, no interest).
  - **Standard case:** uses the canonical amortising-loan formula:
    ```
    EMI = P * r * (1+r)^n / ((1+r)^n - 1)
    ```
    where `P` = principal, `r` = monthly rate, `n` = tenure in months. The result is rounded to 2 decimals (currency precision).
- This is the most fundamental building block — nearly every other function in the module calls `emi()` directly or indirectly.

---

### `total_payment(principal, annual_rate, tenure_months)`

- **Role:** Total amount repaid over the full loan life = `emi * tenure_months`.
- Simply multiplies the EMI (via `emi()`) by the number of instalments, rounded to 2 decimals.

---

### `total_interest(principal, annual_rate, tenure_months)`

- **Role:** Total interest paid over the loan life = `total_payment - principal`.
- Delegates to `total_payment()` and subtracts the original principal.

---

### `amortisation_schedule(principal, annual_rate, tenure_months)`

- **Role:** Builds a month-by-month breakdown of the loan: how much of each instalment goes to interest vs. principal, and the remaining balance after each payment.
- **Algorithm:**
  1. Compute the monthly rate `r` and the fixed `instalment` (EMI).
  2. Iterate `month` from `1` to `tenure_months` (via `range(1, tenure_months)`).
  3. For each month:
     - `interest = balance * r` (interest accrued on the outstanding balance).
     - `principal_part = instalment - interest` (remainder of the EMI that reduces principal).
     - If this is meant to be the final month (`month == tenure_months`), the code instead recalculates `principal_part` as the *entire remaining balance* and recomputes the instalment amount as `principal_part + interest`, to ensure the loan is fully settled even if rounding has left a few cents outstanding. **Note:** because the loop is driven by `range(1, tenure_months)`, `month` never actually reaches `tenure_months` (the range stops at `tenure_months - 1`), so in the current implementation this "final month" branch is unreachable and the returned schedule has `tenure_months - 1` rows instead of the full `tenure_months`. This is a latent off-by-one bug worth being aware of when consuming this function.
     - Update `balance -= principal_part`.
     - Append a dict row: `{month, emi, interest, principal, balance}` (balance floored at `0.0` to avoid tiny negative rounding artifacts).
  4. Returns the list of row dictionaries.
- **Consumers:** `outstanding_after()`, `prepayment_savings()`, `schedule_to_csv()`, and the CLI's `--schedule` flag.

---

### `outstanding_after(principal, annual_rate, tenure_months, months_paid)`

- **Role:** Returns the outstanding loan balance after a given number of EMIs have been paid.
- **Logic:**
  - If `months_paid <= 0`, no payments have been made yet, so the outstanding balance is simply the full `principal`.
  - Otherwise, generates the full `amortisation_schedule()` and looks up the `balance` field at index `months_paid - 1` (schedule rows are 1-indexed by month, list is 0-indexed).
  - If `months_paid` exceeds the number of rows in the schedule (loan already fully repaid), returns `0.0`.
- Effectively a convenience lookup built on top of `amortisation_schedule()`.

---

### `remaining_tenure(balance, annual_rate, instalment)`

- **Role:** Given an outstanding balance, an interest rate, and a fixed instalment amount, calculates how many more months are needed to fully repay the loan.
- **Logic:**
  - `r = annual_rate / 100` — Note this treats `r` as a rate applied directly (not divided by 12 as `_monthly_rate` does elsewhere), so callers must be careful about the rate convention expected here versus `emi()`'s monthly-rate convention.
  - If `balance <= 0`, the loan is already paid off → returns `0`.
  - **Zero-interest case:** if `r == 0`, months needed = `ceil(balance / instalment)` (straight-line division).
  - **Validation:** if `instalment <= balance * r`, the instalment doesn't even cover the first month's interest, so the loan could never be repaid (balance would grow indefinitely) → raises `ValueError("instalment too small to repay the loan")`.
  - **Standard case:** solves the amortisation formula for `n` (number of periods) given a fixed instalment:
    ```
    n = -log(1 - balance*r/instalment) / log(1+r)
    ```
    Result is rounded up (`math.ceil`) since partial months aren't possible — the last month absorbs the remainder.
- **Consumer:** `prepayment_savings()`, to compute how many months remain after a lump-sum prepayment while keeping the EMI unchanged.

---

### `prepayment_savings(principal, annual_rate, tenure_months, prepay_month, prepay_amount)`

> *"Keep the same EMI after a lump-sum prepayment and shorten the tenure."*

- **Role:** Models the effect of making a one-time lump-sum prepayment at a specific month, while keeping the EMI amount unchanged — the saved money instead shortens the loan tenure. Returns interest and time savings.
- **Algorithm:**
  1. Compute the original fixed `instalment` via `emi()`.
  2. Generate the full `amortisation_schedule()` to know the balance at every month.
  3. Look up `balance` at `sched[prepay_month - 1]` — the outstanding balance just before the prepayment is applied at `prepay_month`.
  4. Subtract the lump sum: `new_balance = balance - prepay_amount`.
  5. If `new_balance <= 0`, the loan is fully paid off by the prepayment itself → `months_left = 0`.
  6. Otherwise, call `remaining_tenure(new_balance, annual_rate, instalment)` to find how many more EMIs (at the *same* instalment amount) are needed to clear the reduced balance.
  7. Compute comparison metrics:
     - `original_left = tenure_months - prepay_month` — months that would have remained without prepayment.
     - `interest_paid_so_far` — sum of the `interest` field across all schedule rows up to (and including) `prepay_month`.
     - `original_interest` — total interest that would have been paid over the full original tenure (via `total_interest()`).
     - `new_total` — total amount actually paid in the new scenario: instalments paid before prepayment (`instalment * prepay_month`) + the lump sum itself (`prepay_amount`) + the remaining instalments after prepayment (`instalment * months_left`).
     - `new_interest = new_total - principal` — total interest under the new (prepaid) scenario.
  8. Returns a dict:
     - `emi`: the (unchanged) instalment amount.
     - `months_saved`: how many fewer months are needed (`original_left - months_left`).
     - `new_tenure`: total months to loan closure under the new scenario (`prepay_month + months_left`).
     - `interest_saved`: how much total interest is saved by prepaying (`original_interest - new_interest`).
     - `interest_paid_before_prepayment`: interest already paid up to the point of prepayment, for reference.
- **Note:** This function depends on `amortisation_schedule()`'s indexing (`sched[prepay_month - 1]`), so it inherits that function's off-by-one characteristics described above — for tenures where `prepay_month` is close to `tenure_months`, the schedule may not contain enough rows.

---

### `compare_offers(principal, offers)`

- **Role:** Given a fixed loan principal and a list of competing loan offers from different banks, computes and ranks them by total cost.
- **Input:** `offers` is a list of dicts, each expected to contain `bank`, `rate` (annual %), `tenure` (months), and optionally `processing_fee_pct` (percentage of principal charged as an upfront fee).
- **Algorithm:** For each offer:
  1. Compute `emi()` and `total_interest()` for that offer's rate/tenure.
  2. Compute the processing fee in currency: `fee = processing_fee_pct * principal / 100` (defaults to `0` if the key is absent).
  3. Compute `total_cost = total_interest + processing_fee` — the all-in cost of borrowing beyond the principal itself.
  4. Append a result dict with `bank`, `emi`, `total_interest`, `processing_fee`, `total_cost`.
- Finally, **sorts** the results list in ascending order of `total_cost`, so the cheapest/best offer appears first.
- This is a pure aggregation function that reuses `emi()` and `total_interest()` rather than duplicating amortisation logic.

---

### `eligible_amount(monthly_income, existing_emis, annual_rate, tenure_months, foir=0.5)`

- **Role:** Estimates the maximum loan principal a borrower is eligible for, based on their income and existing debt obligations — a reverse calculation of `emi()`.
- **Concept — FOIR (Fixed Obligation to Income Ratio):** Lenders typically cap total EMI obligations (existing + new) at a fraction of monthly income (default `50%`, i.e. `foir=0.5`).
- **Algorithm:**
  1. `available = monthly_income * foir - existing_emis` — the monthly instalment budget left over for a *new* loan after accounting for the FOIR cap and current EMI commitments.
  2. If `available <= 0`, the borrower cannot afford any new EMI → returns `0.0`.
  3. Compute monthly rate `r` via `_monthly_rate()`.
  4. **Zero-interest case:** if `r == 0`, max principal = `available * tenure_months` (straight-line).
  5. **Standard case:** solves the EMI formula for principal, given a fixed instalment (`available`) and tenure:
     ```
     P = available * ((1+r)^n - 1) / (r * (1+r)^n)
     ```
     This is the algebraic inverse of the `emi()` formula.
- **Use case:** Pre-qualification / affordability checks before a borrower applies for a loan.

---

### `format_inr(amount)`

- **Role:** Formats a numeric amount as an Indian Rupee currency string using the Indian numbering convention (lakhs/crores grouping: groups of 2 digits after the first group of 3), e.g. `1234567.5` → `"₹12,34,567.50"`.
- **Algorithm:**
  1. Capture the sign (`neg`) and work with the absolute value.
  2. Format to 2 decimal places and split into `whole` and `frac` parts via string splitting on `.`.
  3. If the whole part has more than 3 digits, apply Indian-style grouping:
     - Split off the last 3 digits (`tail`) — these stay ungrouped next to the decimal point.
     - Repeatedly peel off 2-digit chunks (`head[-2:]`) from the remaining head and insert them at the front of a `parts` list, until fewer than 3 digits remain in `head`.
     - Any leftover digits (1 or 2) are inserted at the very front.
     - Join `parts` with commas, then append the final comma + `tail`.
  4. Reassemble as `"-"` (if negative) + `"₹"` + grouped whole part + `"."` + fractional part.
- **Consumer:** `summary()`, to present all monetary figures in a human-readable localized format.

---

### `schedule_to_csv(rows, path)`

- **Role:** The only function in the module that performs file I/O. Writes an amortisation schedule (as produced by `amortisation_schedule()`) to a CSV file.
- **Algorithm:**
  1. Opens `path` for writing (truncating/creating as needed).
  2. Writes a header row: `month,emi,interest,principal,balance`.
  3. Iterates over each row dict and writes a comma-separated line with the corresponding values.
- Intended for exporting a schedule for external use (spreadsheets, reporting, etc.). Not currently wired into `cli.py`, but available as part of the public API via `__init__.py`'s wildcard export.

---

### `summary(principal, annual_rate, tenure_months, start=None)`

- **Role:** Produces a human-readable, formatted overview of a loan — the primary "headline" report consumed by the CLI.
- **Algorithm:**
  1. Defaults `start` to today's date (`date.today()`) if not provided — this represents the loan's disbursement/first-EMI date.
  2. Computes the EMI via `emi()`.
  3. Computes the calendar date of the **last EMI**:
     - `end_year = start.year + (start.month - 1 + tenure_months) // 12`
     - `end_month = (start.month - 1 + tenure_months) % 12 + 1`
     - This is standard zero-indexed month arithmetic: convert `start.month` to 0-based, add the tenure, then convert back to 1-based month/year, correctly rolling over year boundaries.
  4. Builds and returns a dict of formatted strings (all monetary figures passed through `format_inr()`):
     - `principal`, `rate` (e.g. `"9.5% p.a."`), `tenure` (e.g. `"36 months"`), `emi`, `total_interest` (via `total_interest()`), `total_payment` (via `total_payment()`), `last_emi` (as `"YYYY-MM"`), and `currency` (the module constant `DEFAULT_CURRENCY`).
- This function is a "facade" that composes `emi()`, `total_interest()`, `total_payment()`, and `format_inr()` into a single ready-to-display result — it's the function the CLI calls first and always prints.

## 4. Data flow / call graph

```
emi() ──────────────┬──> total_payment() ──> total_interest()
                     │                              │
                     ├──> amortisation_schedule()    │
                     │         │                     │
                     │         ├──> outstanding_after()
                     │         └──> prepayment_savings() ──> remaining_tenure()
                     │
                     └──> compare_offers() (calls emi() + total_interest() per offer)

_monthly_rate() ──> used by emi() and eligible_amount()

summary() ──> emi(), total_interest(), total_payment(), format_inr()

schedule_to_csv() ──> consumes rows produced by amortisation_schedule() (I/O boundary)
```

`emi()` is the foundational primitive: almost every higher-level report (`total_payment`, `total_interest`, `amortisation_schedule`, `compare_offers`, `summary`) ultimately depends on it to determine the fixed monthly payment. `amortisation_schedule()` is the second major building block, providing the detailed month-by-month ledger consumed by `outstanding_after()` and `prepayment_savings()`.

## 5. CLI integration (`cli.py`)

`cli.py` is a thin `argparse`-based wrapper that:

1. Parses positional arguments `principal`, `rate`, `tenure`, plus optional flags `--schedule`, `--prepay-month`, `--prepay-amount`.
2. Imports only the three "report-level" functions it needs directly from the package root: `amortisation_schedule`, `prepayment_savings`, and `summary` — demonstrating the `__init__.py` re-export in action.
3. Always calls `summary()` first and prints the result as pretty-printed JSON (`json.dumps(..., indent=2, ensure_ascii=False)`) — `ensure_ascii=False` is required to correctly print the `₹` symbol produced by `format_inr()`.
4. If `--schedule` is passed, calls `amortisation_schedule()` and prints each row dict (one per line, using Python's default `print()` repr, not JSON).
5. If both `--prepay-month` and `--prepay-amount` are supplied, calls `prepayment_savings()` and prints the result as JSON.
6. The `if __name__ == "__main__": main()` guard allows `cli.py` to be run directly as a script (e.g. `python cli.py 500000 9.5 36 --schedule`).

`cli.py` contains no business logic itself — it purely orchestrates argument parsing, function calls into `loan_calc`, and output formatting/printing. This separation means the core `calculator.py` logic can be reused in other contexts (web API, notebook, tests) without depending on `argparse` or console I/O.

## 6. Design observations & potential improvements

- **Rate convention inconsistency:** `_monthly_rate()` (used by `emi`, `eligible_amount`) divides by `1200` (annual % → monthly decimal), while `remaining_tenure()` uses `annual_rate / 100` directly as a *periodic* rate without dividing by 12. Since `remaining_tenure()` is only ever invoked with the same `annual_rate` that was used to compute `instalment` via `emi()`, this inconsistency could introduce subtle inaccuracies in `prepayment_savings()`'s month-count calculation and should be reviewed.
- **Off-by-one in `amortisation_schedule()`:** As noted above, `range(1, tenure_months)` produces `tenure_months - 1` rows, meaning the schedule is always missing its final row and the "settle remaining balance" branch is dead code. This likely needs a fix to `range(1, tenure_months + 1)`.
- **No input validation** beyond `emi()` — functions like `amortisation_schedule`, `remaining_tenure`, and `eligible_amount` don't validate their inputs (e.g. negative tenures, negative balances) as rigorously as `emi()` does.
- **Mutable global state:** None — the module is fully stateless and thread-safe, which is a strength of the current design.
- **Testing:** The `tests/` directory currently only contains a `.gitkeep` placeholder; no automated tests exist yet for any of the functions described above.
