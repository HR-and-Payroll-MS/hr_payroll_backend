import pytest


pytestmark = pytest.mark.skip(reason="payroll app removed with employees; tests skipped to start clean")
import pytest


pytestmark = pytest.mark.skip(reason="payroll app removed with employees; tests skipped to start clean")
    total = comp.recalc_total()

    assert total == Decimal("0.00")
    comp.refresh_from_db()
    assert comp.total_compensation == Decimal("0.00")


@pytest.mark.django_db
def test_negative_offsets_reduce_total():
    user = UserFactory()
    emp = Employee.objects.create(user=user)

    comp = Compensation.objects.create(employee=emp)
    SalaryComponent.objects.create(
        compensation=comp, kind=SalaryComponent.Kind.BASE, amount=Decimal("500.00"), label="Base"
    )
    SalaryComponent.objects.create(
        compensation=comp, kind=SalaryComponent.Kind.OFFSET, amount=Decimal("-600.00"), label="Overpayment Adjustment"
    )

    total = comp.recalc_total()

    assert total == Decimal("-100.00")
    comp.refresh_from_db()
    assert comp.total_compensation == Decimal("-100.00")
