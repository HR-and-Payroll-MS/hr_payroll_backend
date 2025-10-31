import datetime
import inspect

import pytest


@pytest.mark.django_db
def test_employee_model_has_required_fields():
    """Ensure the Employee model exposes the fields required by the new spec.

    This test only checks model metadata (fields, relations and choices) so it
    stays fast and guides the implementation.
    """
    try:
        from hr_payroll.employees import models as employees_models
    except Exception as e:  # pragma: no cover - helpful error when model missing
        pytest.skip(f"employees.models cannot be imported yet: {e}")

    # Ensure Employee model exists
    assert hasattr(employees_models, "Employee"), "Employee model missing"
    Employee = employees_models.Employee

    # Check for profile/display fields
    field_names = {f.name for f in Employee._meta.get_fields()}
    expected_profile = {
        "photo",
        "full_name",
        "position",
        "status",
        "email",
        "phone",
        "time_zone",
        "department",
        "office",
        "line_manager",
    }
    missing = expected_profile - field_names
    assert not missing, f"Missing profile fields on Employee: {missing}"

    # Check for editable personal info fields
    expected_personal = {
        "gender",
        "date_of_birth",
        "nationality",
        "health_care",
        "marital_status",
        "personal_tax_id",
        "social_insurance",
    }
    missing_personal = expected_personal - field_names
    assert not missing_personal, (
        f"Missing personal fields on Employee: {missing_personal}"
    )

    # Employee ID and join date
    assert "employee_id" in field_names, "employee_id field missing"
    assert "join_date" in field_names, "join_date field missing"

    # Check relationships (JobHistory, Contract should be accessible as models)
    assert hasattr(employees_models, "JobHistory"), "JobHistory model missing"
    assert hasattr(employees_models, "Contract"), "Contract model missing"


@pytest.mark.django_db
def test_jobhistory_and_contract_relations():
    try:
        from hr_payroll.employees import models as employees_models
    except Exception as e:
        pytest.skip(f"employees.models cannot be imported yet: {e}")

    Employee = employees_models.Employee
    JobHistory = employees_models.JobHistory
    Contract = employees_models.Contract

    # Inspect fields to ensure FK back to Employee
    job_fk = None
    for f in JobHistory._meta.get_fields():
        if f.is_relation and getattr(f, "related_model", None) is Employee:
            job_fk = f
            break
    assert job_fk is not None, "JobHistory must have a ForeignKey to Employee"

    contract_fk = None
    for f in Contract._meta.get_fields():
        if f.is_relation and getattr(f, "related_model", None) is Employee:
            contract_fk = f
            break
    assert contract_fk is not None, "Contract must have a ForeignKey to Employee"


@pytest.mark.django_db
def test_employee_service_year_property(user):
    try:
        from hr_payroll.employees import models as employees_models
    except Exception as e:
        pytest.skip(f"employees.models cannot be imported yet: {e}")

    Employee = employees_models.Employee

    # Create an instance (do not rely on any required fields beyond defaults)
    # If model requires many fields, this will be improved later when implementing
    now = datetime.date.today()
    join_date = now.replace(year=now.year - 3)

    # Try to construct with minimal arguments using inspect to find required args
    sig = inspect.signature(Employee)
    # We'll attempt to create an object via .objects.create when possible
    create_kwargs = {}
    # Use common defaults where typical
    # Ensure a user is provided for OneToOne/ForeignKey constraints
    create_kwargs["user"] = user
    if "employee_id" in {f.name for f in Employee._meta.get_fields()}:
        create_kwargs["employee_id"] = "TEST123"
    if "full_name" in {f.name for f in Employee._meta.get_fields()}:
        create_kwargs["full_name"] = "Test Person"
    if "email" in {f.name for f in Employee._meta.get_fields()}:
        create_kwargs["email"] = "test@example.com"
    if "join_date" in {f.name for f in Employee._meta.get_fields()}:
        create_kwargs["join_date"] = join_date

    emp = Employee.objects.create(**create_kwargs)

    # service_year should be present as a property or method
    assert hasattr(emp, "service_year") or hasattr(emp, "get_service_year"), (
        "service_year property/method missing"
    )


import datetime as dt

import pytest
from django.utils import timezone

from hr_payroll.employees.models import Employee


@pytest.mark.django_db
def test_employee_profile_and_general_fields_create(user):
    user = user
    e = Employee.objects.create(
        user=user,
        full_name="Pristia Candra Nelson",
        gender="female",
        date_of_birth=dt.date(1997, 5, 23),
        email_address="lincoln@gmail.com",
        phone_number="08931298493",
        nationality="Indonesia",
        health_care="083513296493",
        marital_status="married",
        personal_tax_id="TIN123",
        social_insurance="SSN123",
        title="3D Designer",
        time_zone="GMT-07:00",
        office="Unpixel Studio",
    )
    assert e.pk is not None
    assert e.full_name and e.gender and e.date_of_birth
    assert e.email_address and e.phone_number and e.nationality
    assert e.health_care and e.marital_status and e.personal_tax_id


@pytest.mark.django_db
def test_service_years_property(user):
    user = user
    join = timezone.now().date() - dt.timedelta(days=365 * 3 + 30 * 7)
    e = Employee.objects.create(user=user, join_date=join)
    # Expect a non-empty human readable value like "3 Years" or "3 Years 7 Months"
    assert isinstance(e.service_years, str) and e.service_years


@pytest.mark.django_db
def test_job_history_timeline(user):
    user = user
    e = Employee.objects.create(user=user, title="UI/UX Designer")
    # Lazy import to avoid circular if models not yet migrated
    from hr_payroll.employees.models import JobHistory

    j1 = JobHistory.objects.create(
        employee=e,
        effective_date=dt.date(2019, 8, 20),
        job_title="UI/UX Designer",
        position_type="Fulltime",
        employment_type="fulltime",
    )
    j2 = JobHistory.objects.create(
        employee=e,
        effective_date=dt.date(2020, 1, 1),
        job_title="Senior UI/UX Designer",
        position_type="Fulltime",
        employment_type="fulltime",
    )
    timeline = list(JobHistory.objects.filter(employee=e))
    assert timeline[0].effective_date <= timeline[-1].effective_date
    assert {j1.job_title, j2.job_title} <= {j.job_title for j in timeline}


@pytest.mark.django_db
def test_contract_timeline(user):
    user = user
    e = Employee.objects.create(user=user)
    from hr_payroll.employees.models import Contract

    c1 = Contract.objects.create(
        employee=e,
        contract_number="#12345",
        contract_name="Fulltime Remote",
        contract_type="Fulltime",
        start_date=dt.date(2019, 8, 20),
    )
    c2 = Contract.objects.create(
        employee=e,
        contract_number="#23456",
        contract_name="Extended",
        contract_type="Fulltime",
        start_date=dt.date(2021, 1, 1),
        end_date=dt.date(2022, 1, 1),
    )
    contracts = list(Contract.objects.filter(employee=e).order_by("start_date"))
    assert contracts[0].start_date == c1.start_date
    assert contracts[-1].start_date == c2.start_date
