import django_filters

from hr_payroll.employees.models import Employee


class EmployeeFilter(django_filters.FilterSet):
    gender = django_filters.CharFilter(
        field_name="user__profile__gender", lookup_expr="iexact"
    )
    employment_type = django_filters.CharFilter(
        field_name="job_history__employment_type", lookup_expr="iexact"
    )
    status = django_filters.BooleanFilter(field_name="is_active")
    department = django_filters.NumberFilter(field_name="department__id")

    class Meta:
        model = Employee
        fields = ["gender", "employment_type", "status", "department"]
