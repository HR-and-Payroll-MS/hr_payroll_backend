from decimal import Decimal

from hr_payroll.payroll.services import prorate_amount


def test_prorate_amount_basic():
    assert prorate_amount(
        Decimal("3000.00"), worked_days=15, period_days=30
    ) == Decimal("1500.00")


def test_prorate_amount_zero_period():
    assert prorate_amount(Decimal("3000.00"), worked_days=10, period_days=0) == Decimal(
        "0.00"
    )


def test_prorate_amount_rounding():
    # 10/31 of 3000 = 967.7419 -> 967.74
    assert prorate_amount(
        Decimal("3000.00"), worked_days=10, period_days=31
    ) == Decimal("967.74")
