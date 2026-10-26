# -*- coding: utf-8 -*-
from loan_calc.calculator import emi

# Test: EMI for 10,00,000 at 9% p.a. over 240 months matches 8,997 (± 1)
result = emi(1000000, 9, 240)
expected = 8997
tolerance = 1

print('EMI Calculation: 10,00,000 at 9% p.a. over 240 months')
print('Result: {:.2f}'.format(result))
print('Expected: {:.2f} (±{})'.format(expected, tolerance))
print('Match: {}'.format(expected - tolerance <= result <= expected + tolerance))

if expected - tolerance <= result <= expected + tolerance:
    print('TEST PASSED')
else:
    print('TEST FAILED')
