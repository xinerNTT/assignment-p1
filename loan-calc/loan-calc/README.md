# loan-calc

A comprehensive Python module for retail loan calculations: EMI, amortisation schedule, prepayment savings, offer comparison and eligibility.

## Features

- ✅ **Fixed**: 3 critical bugs (rounding, rate calculation, prepayment interest)
- ✅ **Tested**: 80 comprehensive tests with 98% code coverage
- ✅ **Documented**: Full type hints and docstrings for all public functions
- ✅ **Edge Cases**: Handles 0% interest, large principals, short tenures, and prepayment edge cases

## Setup

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .
```

## Try it

```bash
python cli.py 1000000 9 240
python cli.py 1000000 9 240 --schedule
python cli.py 1000000 9 240 --prepay-month 24 --prepay-amount 200000
```

## Run Tests

All tests pass with 98% code coverage:

```bash
pytest --cov=loan_calc --cov-report=term-missing
```

### Test Coverage
- **80 tests** across all calculator functions
- **Edge cases**: 0% interest, very large principals, 1-month tenure, prepayment scenarios
- **Coverage**: 98% of statements covered

### Test Files
- `test_calculator.py` - Main test suite covering all functions
- `test_emi_manual.py` - Manual EMI calculation validation
- `test_remaining_tenure_edge_cases.py` - Comprehensive edge-case tests for tenure calculations

## Bug Fixes

### 1. _monthly_rate() - Rounding Precision
**Issue**: 4-decimal rounding caused cumulative errors in long-tenure loans
**Fix**: Removed rounding to use full float precision
**Impact**: Corrected amortisation schedules for all tenures

### 2. remaining_tenure() - Rate Inconsistency
**Issue**: Used `annual_rate / 100` instead of monthly rate, causing incorrect tenure calculations
**Fix**: Changed to use `_monthly_rate()` for consistency
**Impact**: Accurate remaining tenure and prepayment calculations

### 3. prepayment_savings() - Negative Interest Bug
**Issue**: Interest savings could be negative due to incorrect calculation
**Fix**: Properly compute `interest_after` to get correct savings
**Impact**: Accurate prepayment impact analysis

## Architecture

See [ARCHITECTURE.md](loan_calc/ARCHITECTURE.md) for detailed design documentation.
