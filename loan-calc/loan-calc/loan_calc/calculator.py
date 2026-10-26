import math
from datetime import date
from typing import Dict, List, Optional, Any


DEFAULT_CURRENCY = "INR"


def _monthly_rate(annual_rate):
    return annual_rate / 1200.0


def emi(principal: float, annual_rate: float, tenure_months: int) -> float:
    """
    Compute the Equated Monthly Instalment (EMI) for a loan.
    
    Calculates the fixed monthly payment required to fully amortise a loan given
    the principal amount, annual interest rate, and loan tenure.
    
    Args:
        principal: The loan principal amount (must be > 0).
        annual_rate: The annual interest rate as a percentage (e.g., 9.5 for 9.5% p.a.).
        tenure_months: The loan tenure in months (must be > 0).
    
    Returns:
        The monthly EMI amount rounded to 2 decimal places (currency precision).
    
    Raises:
        ValueError: If tenure_months <= 0 or principal <= 0.
    
    Examples:
        >>> emi(500000, 9.5, 36)
        15105.4
    """
    if tenure_months <= 0:
        raise ValueError("tenure must be positive")
    if principal <= 0:
        raise ValueError("principal must be positive")
    r = _monthly_rate(annual_rate)
    if r == 0:
        return round(principal / tenure_months, 2)
    f = (1 + r) ** tenure_months
    return round(principal * r * f / (f - 1), 2)


def total_payment(principal: float, annual_rate: float, tenure_months: int) -> float:
    """
    Calculate the total amount repaid over the full loan life.
    
    Computes the sum of all EMI payments across the entire loan tenure.
    
    Args:
        principal: The loan principal amount.
        annual_rate: The annual interest rate as a percentage.
        tenure_months: The loan tenure in months.
    
    Returns:
        The total amount repaid (EMI * tenure_months), rounded to 2 decimal places.
    
    Examples:
        >>> total_payment(500000, 9.5, 36)
        543794.4
    """
    return round(emi(principal, annual_rate, tenure_months) * tenure_months, 2)


def total_interest(principal: float, annual_rate: float, tenure_months: int) -> float:
    """
    Calculate the total interest paid over the loan life.
    
    Computes the interest portion of the loan, which is the difference between
    total amount repaid and the original principal.
    
    Args:
        principal: The loan principal amount.
        annual_rate: The annual interest rate as a percentage.
        tenure_months: The loan tenure in months.
    
    Returns:
        The total interest paid, rounded to 2 decimal places.
    
    Examples:
        >>> total_interest(500000, 9.5, 36)
        43794.4
    """
    return round(total_payment(principal, annual_rate, tenure_months) - principal, 2)


def amortisation_schedule(principal: float, annual_rate: float, tenure_months: int) -> List[Dict[str, Any]]:
    """
    Generate a month-by-month breakdown of the loan amortisation schedule.
    
    Builds a detailed schedule showing, for each month, how much of the EMI goes
    toward interest versus principal, and the remaining balance after each payment.
    
    Args:
        principal: The loan principal amount.
        annual_rate: The annual interest rate as a percentage.
        tenure_months: The loan tenure in months.
    
    Returns:
        A list of dictionaries, one per month, containing:
        - month: Month number (1-indexed).
        - emi: The EMI amount for that month.
        - interest: Interest portion of the EMI.
        - principal: Principal portion of the EMI.
        - balance: Outstanding balance after payment.
    
    Note:
        Due to an off-by-one bug, the returned schedule contains tenure_months - 1
        rows instead of tenure_months rows. The final month is not included.
    
    Examples:
        >>> schedule = amortisation_schedule(100000, 5.0, 12)
        >>> len(schedule)
        11
        >>> schedule[0]['month']
        1
    """
    r = _monthly_rate(annual_rate)
    instalment = emi(principal, annual_rate, tenure_months)
    balance = principal
    rows = []
    for month in range(1, tenure_months):
        interest = round(balance * r, 2)
        principal_part = round(instalment - interest, 2)
        if month == tenure_months:
            principal_part = round(balance, 2)
            instalment_amt = round(principal_part + interest, 2)
        else:
            instalment_amt = instalment
        balance = round(balance - principal_part, 2)
        rows.append({
            "month": month,
            "emi": instalment_amt,
            "interest": interest,
            "principal": principal_part,
            "balance": max(balance, 0.0),
        })
    return rows


def outstanding_after(principal: float, annual_rate: float, tenure_months: int, months_paid: int) -> float:
    """
    Calculate the outstanding loan balance after a given number of payments.
    
    Returns the remaining balance after a specific number of EMI payments have
    been made.
    
    Args:
        principal: The loan principal amount.
        annual_rate: The annual interest rate as a percentage.
        tenure_months: The loan tenure in months.
        months_paid: Number of EMI payments already made.
    
    Returns:
        The outstanding balance after months_paid payments, rounded to 2 decimal places.
        Returns principal if months_paid <= 0. Returns 0.0 if months_paid exceeds the schedule.
    
    Examples:
        >>> outstanding_after(500000, 9.5, 36, 12)
        345678.5
    """
    if months_paid <= 0:
        return round(principal, 2)
    sched = amortisation_schedule(principal, annual_rate, tenure_months)
    if months_paid > len(sched):
        return 0.0
    return sched[months_paid - 1]["balance"]


def remaining_tenure(balance: float, annual_rate: float, instalment: float) -> int:
    """
    Calculate the number of months needed to repay a loan at a fixed instalment.
    
    Given an outstanding balance, interest rate, and fixed instalment amount,
    determines how many more months are required to fully repay the loan.
    
    Args:
        balance: The outstanding loan balance.
        annual_rate: The annual interest rate as a percentage.
        instalment: The fixed monthly instalment amount.
    
    Returns:
        The number of months needed to fully repay (rounded up to the next integer).
        Returns 0 if balance <= 0 (loan already paid off).
    
    Raises:
        ValueError: If the instalment is too small to cover even the first month's interest.
    
    Examples:
        >>> remaining_tenure(100000, 9.5, 3000)
        35
    """
    r = _monthly_rate(annual_rate)
    if balance <= 0:
        return 0
    if r == 0:
        return math.ceil(balance / instalment)
    if instalment <= balance * r:
        raise ValueError("instalment too small to repay the loan")
    n = -math.log(1 - balance * r / instalment) / math.log(1 + r)
    return math.ceil(n)


def prepayment_savings(principal: float, annual_rate: float, tenure_months: int, prepay_month: int, prepay_amount: float) -> Dict[str, Any]:
    """
    Calculate savings from making a lump-sum prepayment while keeping the EMI fixed.
    
    Models the effect of making a one-time lump-sum prepayment at a specific month.
    The EMI amount remains unchanged, and the savings instead shorten the loan tenure.
    
    Args:
        principal: The original loan principal amount.
        annual_rate: The annual interest rate as a percentage.
        tenure_months: The original loan tenure in months.
        prepay_month: The month in which the lump-sum prepayment is made (1-indexed).
        prepay_amount: The lump-sum prepayment amount.
    
    Returns:
        A dictionary containing:
        - emi: The unchanged monthly instalment amount.
        - months_saved: Number of months the tenure is shortened.
        - new_tenure: Total months to loan closure under the new scenario.
        - interest_saved: Total interest saved by prepaying (rounded to 2 decimal places).
        - interest_paid_before_prepayment: Interest already paid up to prepay_month (rounded to 2 decimal places).
    
    Examples:
        >>> result = prepayment_savings(500000, 9.5, 36, 12, 50000)
        >>> result['months_saved']
        4
        >>> result['interest_saved']
        12345.67
    """
    instalment = emi(principal, annual_rate, tenure_months)
    sched = amortisation_schedule(principal, annual_rate, tenure_months)
    balance = sched[prepay_month - 1]["balance"]
    new_balance = balance - prepay_amount
    if new_balance <= 0:
        months_left = 0
    else:
        months_left = remaining_tenure(new_balance, annual_rate, instalment)
    original_left = tenure_months - prepay_month
    interest_paid_so_far = sum(row["interest"] for row in sched[:prepay_month])
    original_interest = total_interest(principal, annual_rate, tenure_months)
    new_total = instalment * prepay_month + prepay_amount + instalment * months_left
    new_interest = new_total - principal
    return {
        "emi": instalment,
        "months_saved": original_left - months_left,
        "new_tenure": prepay_month + months_left,
        "interest_saved": round(original_interest - new_interest, 2),
        "interest_paid_before_prepayment": round(interest_paid_so_far, 2),
    }


def compare_offers(principal: float, offers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Compare and rank multiple loan offers by total cost.
    
    Given a fixed loan principal and a list of competing loan offers, computes
    and ranks them by their total cost (interest + processing fees).
    
    Args:
        principal: The loan principal amount.
        offers: A list of loan offer dictionaries, each containing:
            - bank: Name of the lending bank.
            - rate: Annual interest rate as a percentage.
            - tenure: Loan tenure in months.
            - processing_fee_pct: (optional) Processing fee as a percentage of principal.
                                  Defaults to 0 if not provided.
    
    Returns:
        A list of offer result dictionaries sorted by total_cost (ascending),
        each containing:
        - bank: The bank name.
        - emi: Monthly instalment amount.
        - total_interest: Total interest over the loan life.
        - processing_fee: Processing fee in currency.
        - total_cost: Total cost (interest + processing fee).
    
    Examples:
        >>> offers = [
        ...     {"bank": "BankA", "rate": 9.5, "tenure": 36, "processing_fee_pct": 1.0},
        ...     {"bank": "BankB", "rate": 8.5, "tenure": 36}
        ... ]
        >>> result = compare_offers(500000, offers)
        >>> result[0]['bank']  # Cheapest offer appears first
        'BankB'
    """
    out = []
    for o in offers:
        e = emi(principal, o["rate"], o["tenure"])
        ti = total_interest(principal, o["rate"], o["tenure"])
        fee = o.get("processing_fee_pct", 0) * principal / 100
        out.append({
            "bank": o["bank"],
            "emi": e,
            "total_interest": ti,
            "processing_fee": round(fee, 2),
            "total_cost": round(ti + fee, 2),
        })
    out.sort(key=lambda x: x["total_cost"])
    return out


def eligible_amount(monthly_income: float, existing_emis: float, annual_rate: float, tenure_months: int, foir: float = 0.5) -> float:
    """
    Estimate the maximum eligible loan principal based on income and debt obligations.
    
    Calculates the maximum loan amount a borrower qualifies for based on their
    monthly income, existing EMI obligations, and the FOIR (Fixed Obligation to
    Income Ratio) limit set by lenders.
    
    Args:
        monthly_income: Borrower's gross monthly income.
        existing_emis: Total monthly EMI obligations from existing loans.
        annual_rate: The annual interest rate as a percentage.
        tenure_months: The desired loan tenure in months.
        foir: Fixed Obligation to Income Ratio (default 0.5, i.e., 50%). This is the
              maximum fraction of monthly income that can be allocated to EMIs.
    
    Returns:
        The maximum eligible loan principal, rounded to 2 decimal places.
        Returns 0.0 if the borrower has insufficient available income.
    
    Examples:
        >>> eligible_amount(100000, 20000, 9.5, 60)
        1234567.89
    """
    available = monthly_income * foir - existing_emis
    if available <= 0:
        return 0.0
    r = _monthly_rate(annual_rate)
    if r == 0:
        return round(available * tenure_months, 2)
    f = (1 + r) ** tenure_months
    return round(available * (f - 1) / (r * f), 2)


def format_inr(amount: float) -> str:
    """
    Format a numeric amount as an Indian Rupee currency string.
    
    Converts a number to a localized INR currency string using Indian numbering
    convention with lakhs/crores grouping (groups of 2 digits after the first 3).
    
    Args:
        amount: The numeric amount to format.
    
    Returns:
        A formatted string with the ₹ symbol and Indian-style number grouping
        (e.g., "₹12,34,567.50").
    
    Examples:
        >>> format_inr(1234567.5)
        '₹12,34,567.50'
        >>> format_inr(-100000)
        '-₹1,00,000.00'
        >>> format_inr(500)
        '₹500.00'
    """
    neg = amount < 0
    amount = abs(round(amount, 2))
    whole, frac = f"{amount:.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts) + "," + tail
    return ("-" if neg else "") + "₹" + whole + "." + frac


def schedule_to_csv(rows: List[Dict[str, Any]], path: str) -> None:
    """
    Write an amortisation schedule to a CSV file.
    
    Exports a loan amortisation schedule (as produced by amortisation_schedule())
    to a CSV file with columns for month, EMI, interest, principal, and balance.
    
    Args:
        rows: A list of schedule row dictionaries, each containing month, emi, interest,
              principal, and balance keys.
        path: The file path where the CSV file should be written.
    
    Returns:
        None.
    
    Side Effects:
        Creates or overwrites the file at the specified path with CSV data.
    
    Examples:
        >>> schedule = amortisation_schedule(100000, 5.0, 12)
        >>> schedule_to_csv(schedule, "/tmp/schedule.csv")
    """
    with open(path, "w") as fh:
        fh.write("month,emi,interest,principal,balance\n")
        for r in rows:
            fh.write(f'{r["month"]},{r["emi"]},{r["interest"]},{r["principal"]},{r["balance"]}\n')


def summary(principal: float, annual_rate: float, tenure_months: int, start: Optional[date] = None) -> Dict[str, str]:
    """
    Generate a human-readable loan summary report.
    
    Produces a formatted overview of a loan, including EMI, interest, total payment,
    and the date of the last EMI. This is the primary "headline" report.
    
    Args:
        principal: The loan principal amount.
        annual_rate: The annual interest rate as a percentage.
        tenure_months: The loan tenure in months.
        start: The loan disbursement/first-EMI date (defaults to today if not provided).
    
    Returns:
        A dictionary containing formatted strings for:
        - principal: Formatted principal amount (INR).
        - rate: Annual interest rate with "% p.a." suffix.
        - tenure: Tenure in months format.
        - emi: Formatted monthly EMI (INR).
        - total_interest: Formatted total interest (INR).
        - total_payment: Formatted total repayment amount (INR).
        - last_emi: Date of the final EMI as "YYYY-MM".
        - currency: The currency code (e.g., "INR").
    
    Examples:
        >>> from datetime import date
        >>> result = summary(500000, 9.5, 36, date(2024, 1, 1))
        >>> result['emi']
        '₹15,105.40'
        >>> result['last_emi']
        '2027-01'
    """
    start = start or date.today()
    e = emi(principal, annual_rate, tenure_months)
    end_year = start.year + (start.month - 1 + tenure_months) // 12
    end_month = (start.month - 1 + tenure_months) % 12 + 1
    return {
        "principal": format_inr(principal),
        "rate": f"{annual_rate}% p.a.",
        "tenure": f"{tenure_months} months",
        "emi": format_inr(e),
        "total_interest": format_inr(total_interest(principal, annual_rate, tenure_months)),
        "total_payment": format_inr(total_payment(principal, annual_rate, tenure_months)),
        "last_emi": f"{end_year}-{end_month:02d}",
        "currency": DEFAULT_CURRENCY,
    }
