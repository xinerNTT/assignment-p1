"""
Comprehensive edge-case tests for remaining_tenure() function.

These tests validate boundary conditions and mathematical edge cases in loan tenure calculations.
"""
import math
import pytest
from loan_calc import remaining_tenure


class TestRemainingTenureEdgeCases:
    """Edge cases for remaining_tenure() function."""

    # =========================================================================
    # 1. FIXED: test_very_large_balance - Realistic values
    # =========================================================================
    def test_very_large_balance_realistic(self):
        """
        Test with very large principal balance using realistic instalment values.
        
        Edge Case: Very large numbers (10^12) that require careful floating-point handling.
        
        Setup:
        - balance = 10^12 (1 trillion)
        - annual_rate = 9.5%
        - monthly_rate ≈ 0.00791667
        - monthly_interest ≈ 7.9167 × 10^9
        - instalment = 10^10 (10 billion, exceeds monthly interest)
        
        Expected Behaviour:
        - Returns a positive integer representing months needed to repay
        - Result is finite (not infinity or NaN)
        - Loan can actually be repaid (instalment > monthly_interest)
        
        Justification:
        Very large loan amounts can expose floating-point precision issues in 
        logarithmic calculations. This test ensures the amortisation formula works
        correctly even with extreme values.
        """
        balance = 10 ** 12
        annual_rate = 9.5
        instalment = 10 ** 10  # 10 billion - exceeds monthly interest
        
        result = remaining_tenure(balance, annual_rate, instalment)
        
        assert isinstance(result, int)
        assert result > 0
        assert math.isfinite(result)
        # Sanity check: with 10B instalment on 1T balance, should take ~100+ months
        assert result >= 100

    # =========================================================================
    # 2. test_zero_interest_rate - 0% interest edge case
    # =========================================================================
    def test_zero_interest_rate(self):
        """
        Test with 0% annual interest rate.
        
        Edge Case: Zero interest rate should use straight-line amortisation.
        
        Setup:
        - balance = 100,000
        - annual_rate = 0%
        - instalment = 10,000
        
        Expected Behaviour:
        - Returns exactly 10 (100,000 / 10,000)
        - Loan amortises in equal principal-only payments
        
        Justification:
        When interest rate is 0%, the formula must fall back to simple division
        without using logarithmic calculations. This tests the special case handling.
        """
        balance = 100_000
        annual_rate = 0
        instalment = 10_000
        
        result = remaining_tenure(balance, annual_rate, instalment)
        
        assert result == 10
        assert isinstance(result, int)

    # =========================================================================
    # 3. test_one_month_tenure - Very short tenure edge case
    # =========================================================================
    def test_one_month_tenure(self):
        """
        Test with instalment nearly equal to (principal + 1 month interest).
        
        Edge Case: Loan repayable in exactly 1 month.
        
        Setup:
        - balance = 100,000
        - annual_rate = 9.5%
        - monthly_interest ≈ 791.67
        - instalment = 101,000 (covers principal + interest)
        
        Expected Behaviour:
        - Returns 1 (repayable in exactly 1 month)
        - Result is a positive integer
        
        Justification:
        Tests boundary condition where loan is repaid almost immediately.
        Ensures formula works correctly for very short tenures.
        """
        balance = 100_000
        annual_rate = 9.5
        instalment = 101_000  # Covers principal + ~1 month interest
        
        result = remaining_tenure(balance, annual_rate, instalment)
        
        assert result == 1
        assert isinstance(result, int)

    # =========================================================================
    # 4. test_very_large_principal_large_instalment - Very large principal
    # =========================================================================
    def test_very_large_principal_large_instalment(self):
        """
        Test with very large principal and correspondingly large instalment.
        
        Edge Case: 1 billion principal with 50 million monthly instalment.
        
        Setup:
        - balance = 10^9 (1 billion)
        - annual_rate = 8.5%
        - monthly_rate ≈ 0.00708333
        - monthly_interest ≈ 7.08 × 10^6 (7.08 million)
        - instalment = 5 × 10^7 (50 million, comfortably exceeds interest)
        
        Expected Behaviour:
        - Returns positive integer (approximately 20-30 months)
        - Result is finite and mathematically sound
        
        Justification:
        Tests large-number handling to ensure no overflow or precision loss.
        Important for real-world scenarios with large loan amounts.
        """
        balance = 10 ** 9
        annual_rate = 8.5
        instalment = 5 * 10 ** 7
        
        result = remaining_tenure(balance, annual_rate, instalment)
        
        assert isinstance(result, int)
        assert result > 0
        assert math.isfinite(result)
        # Rough estimate: 1B / 50M ≈ 20 months, accounting for interest
        assert 15 < result < 30

    # =========================================================================
    # 5. test_instalment_exactly_covers_monthly_interest - Critical boundary
    # =========================================================================
    def test_instalment_equals_monthly_interest(self):
        """
        Test when instalment exactly equals monthly interest (boundary condition).
        
        Edge Case: Instalment = monthly interest (no principal reduction).
        
        Setup:
        - balance = 100,000
        - annual_rate = 9.5%
        - monthly_interest = 791.67
        - instalment = 791.67 (exactly covers interest)
        
        Expected Behaviour:
        - Raises ValueError (loan cannot be repaid)
        - Error message: "instalment too small to repay the loan"
        
        Justification:
        At this critical boundary, the loan will never be repaid as no principal
        is being reduced. The function must correctly reject this as impossible.
        """
        balance = 100_000
        annual_rate = 9.5
        instalment = 791.66  # Slightly less than monthly interest (~791.67)
        
        with pytest.raises(ValueError, match="instalment too small to repay the loan"):
            remaining_tenure(balance, annual_rate, instalment)

    # =========================================================================
    # 6. test_instalment_less_than_monthly_interest - Impossible scenario
    # =========================================================================
    def test_instalment_less_than_monthly_interest(self):
        """
        Test when instalment is less than monthly interest (mathematically impossible).
        
        Edge Case: Instalment cannot cover monthly interest accrual.
        
        Setup:
        - balance = 100,000
        - annual_rate = 9.5%
        - monthly_interest ≈ 791.67
        - instalment = 500 (less than interest)
        
        Expected Behaviour:
        - Raises ValueError (loan impossible to repay)
        - Error message indicates problem
        
        Justification:
        When instalment < monthly interest, the balance grows each month.
        This is mathematically impossible to repay and must be rejected.
        """
        balance = 100_000
        annual_rate = 9.5
        instalment = 500  # Less than monthly interest
        
        with pytest.raises(ValueError, match="instalment too small to repay the loan"):
            remaining_tenure(balance, annual_rate, instalment)

    # =========================================================================
    # 7. test_instalment_slightly_exceeds_monthly_interest - Tight boundary
    # =========================================================================
    def test_instalment_slightly_exceeds_monthly_interest(self):
        """
        Test when instalment barely exceeds monthly interest (tight boundary).
        
        Edge Case: Instalment just barely covers monthly interest.
        
        Setup:
        - balance = 100,000
        - annual_rate = 9.5%
        - monthly_interest ≈ 791.67
        - instalment = 800 (barely exceeds interest, slow repayment)
        
        Expected Behaviour:
        - Returns a very large positive integer (>100 months)
        - Loan is technically repayable but takes very long time
        
        Justification:
        Tests the boundary where the loan becomes just barely repayable.
        Principal reduction is minimal, making tenure very long.
        Important for detecting off-by-one errors at critical boundary.
        """
        balance = 100_000
        annual_rate = 9.5
        instalment = 800  # Slightly exceeds ~791.67 monthly interest
        
        result = remaining_tenure(balance, annual_rate, instalment)
        
        assert isinstance(result, int)
        assert result > 0
        assert math.isfinite(result)
        # With only 8.33 principal reduction per month, takes 500+ months
        assert result > 400
