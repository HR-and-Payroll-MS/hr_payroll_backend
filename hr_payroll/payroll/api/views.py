from django.db.models import Sum
from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import extend_schema_view
from rest_framework import serializers
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAdminUser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from hr_payroll.employees.models import Employee
from hr_payroll.payroll.models import BankDetail
from hr_payroll.payroll.models import Compensation
from hr_payroll.payroll.models import Dependent
from hr_payroll.payroll.models import PayrollCycle
from hr_payroll.payroll.models import PayrollRecord
from hr_payroll.payroll.models import SalaryComponent
from hr_payroll.payroll.services import generate_payroll_for_cycle

from .serializers import BankDetailSerializer
from .serializers import CompensationSerializer
from .serializers import DependentSerializer
from .serializers import PayrollCycleSerializer
from .serializers import PayrollRecordSerializer
from .serializers import SalaryComponentSerializer


@extend_schema_view(
    list=extend_schema(tags=["Payroll • Compensations"]),
    retrieve=extend_schema(tags=["Payroll • Compensations"]),
    create=extend_schema(tags=["Payroll • Compensations"]),
    update=extend_schema(tags=["Payroll • Compensations"]),
    partial_update=extend_schema(tags=["Payroll • Compensations"]),
    destroy=extend_schema(tags=["Payroll • Compensations"]),
)
class CompensationViewSet(viewsets.ModelViewSet):
    queryset = Compensation.objects.select_related("employee").prefetch_related(
        "components"
    )
    serializer_class = CompensationSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request and self.request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            return [IsAdminUser()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        # Support nested route: /employees/{employee_id}/compensations/
        employee = self.kwargs.get("employee_id") or self.request.query_params.get(
            "employee"
        )
        if employee:
            qs = qs.filter(employee_id=employee)
        return qs

    def get_serializer(self, *args, **kwargs):
        # If nested under an employee AND we're performing a write,
        # make 'employee' field optional/read-only so payload needn't include it.
        serializer = super().get_serializer(*args, **kwargs)
        if (
            self.request
            and self.request.method in {"POST", "PUT", "PATCH"}
            and self.kwargs.get("employee_id")
        ):
            target = getattr(serializer, "child", None) or serializer
            if hasattr(target, "fields") and "employee" in target.fields:
                target.fields["employee"].required = False
                target.fields["employee"].read_only = True
        return serializer

    def perform_create(self, serializer):
        # Bind employee automatically when using nested route; otherwise use payload
        employee_id = self.kwargs.get("employee_id")
        if employee_id:
            # Validate the employee exists to avoid blind exception handling
            if not Employee.objects.filter(pk=employee_id).exists():
                msg = "Employee not found."
                raise NotFound(msg)
            serializer.save(employee_id=employee_id)
        else:
            serializer.save()

    @action(
        detail=True,
        methods=["post"],
        url_path="apply-to-employee",
        permission_classes=[IsAdminUser],
    )
    def apply_to_employee(self, request, pk=None):
        """
        Clone this compensation's components into a new compensation for the
        target employee.

        Body: { "employee": "<employee_id>" }
        Returns the created Compensation payload.
        """
        target_employee = request.data.get("employee")
        if not target_employee:
            raise ValidationError({"employee": "This field is required."})

        try:
            source = self.get_queryset().get(pk=pk)
        except Compensation.DoesNotExist:
            msg = "Compensation not found."
            raise NotFound(msg) from None

        # Create a new compensation for the target employee and copy components
        new_comp = Compensation.objects.create(employee_id=target_employee)
        comps = [
            SalaryComponent(
                compensation=new_comp,
                kind=c.kind,
                amount=c.amount,
                label=c.label,
            )
            for c in source.components.all()
        ]
        if comps:
            SalaryComponent.objects.bulk_create(comps)
        new_comp.recalc_total()

        serializer = self.get_serializer(new_comp)
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(tags=["Payroll • Salary Components"]),
    retrieve=extend_schema(tags=["Payroll • Salary Components"]),
    create=extend_schema(tags=["Payroll • Salary Components"]),
    update=extend_schema(tags=["Payroll • Salary Components"]),
    partial_update=extend_schema(tags=["Payroll • Salary Components"]),
    destroy=extend_schema(tags=["Payroll • Salary Components"]),
)
class SalaryComponentViewSet(viewsets.ModelViewSet):
    queryset = SalaryComponent.objects.select_related("compensation")
    serializer_class = SalaryComponentSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request and self.request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            return [IsAdminUser()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        # Support doubly nested route:
        # /employees/{employee_id}/compensations/{compensation_id}/salary-components/
        compensation = self.kwargs.get(
            "compensation_id"
        ) or self.request.query_params.get("compensation")
        employee = self.kwargs.get("employee_id") or self.request.query_params.get(
            "employee"
        )
        if employee:
            qs = qs.filter(compensation__employee_id=employee)
        if compensation:
            qs = qs.filter(compensation_id=compensation)
        return qs

    def get_serializer(self, *args, **kwargs):
        serializer = super().get_serializer(*args, **kwargs)
        # When doubly nested, make 'compensation' read-only on writes
        if (
            self.request
            and self.request.method in {"POST", "PUT", "PATCH"}
            and self.kwargs.get("employee_id")
            and self.kwargs.get("compensation_id")
        ):
            target = getattr(serializer, "child", None) or serializer
            if hasattr(target, "fields") and "compensation" in target.fields:
                target.fields["compensation"].required = False
                target.fields["compensation"].read_only = True
        return serializer

    def perform_create(self, serializer):
        # Enforce double nesting and ownership: the compensation must belong
        # to the employee
        comp_id = self.kwargs.get("compensation_id")
        emp_id = self.kwargs.get("employee_id")
        if comp_id and emp_id:
            try:
                comp = Compensation.objects.get(pk=comp_id, employee_id=emp_id)
            except Compensation.DoesNotExist:
                msg = "Compensation not found for this employee."
                raise NotFound(msg) from None
            instance = serializer.save(compensation=comp)
        else:
            # Fallback for non-nested calls (shouldn't be routed anymore)
            instance = serializer.save()
        # Recalculate totals on parent compensation
        instance.compensation.recalc_total()

    def perform_update(self, serializer):
        instance = serializer.save()
        instance.compensation.recalc_total()

    def perform_destroy(self, instance):
        comp = instance.compensation
        super().perform_destroy(instance)
        comp.recalc_total()


@extend_schema_view(
    list=extend_schema(tags=["Payroll • Cycles"]),
    retrieve=extend_schema(tags=["Payroll • Cycles"]),
    create=extend_schema(tags=["Payroll • Cycles"]),
    update=extend_schema(tags=["Payroll • Cycles"]),
    partial_update=extend_schema(tags=["Payroll • Cycles"]),
    destroy=extend_schema(tags=["Payroll • Cycles"]),
)
class PayrollCycleViewSet(viewsets.ModelViewSet):
    queryset = PayrollCycle.objects.all().prefetch_related("eligible_employees")
    serializer_class = PayrollCycleSerializer
    permission_classes = [IsAdminUser]

    def perform_create(self, serializer):
        # Basic validation: period_start must be <= period_end
        period_start = serializer.validated_data.get("period_start")
        period_end = serializer.validated_data.get("period_end")
        if period_start and period_end and period_start > period_end:
            raise ValidationError({"period_end": "period_end must be >= period_start"})
        serializer.save()


@extend_schema_view(
    list=extend_schema(tags=["Payroll • Records"]),
    retrieve=extend_schema(tags=["Payroll • Records"]),
    create=extend_schema(tags=["Payroll • Records"]),
    update=extend_schema(tags=["Payroll • Records"]),
    partial_update=extend_schema(tags=["Payroll • Records"]),
    destroy=extend_schema(tags=["Payroll • Records"]),
)
class PayrollRecordViewSet(viewsets.ModelViewSet):
    queryset = PayrollRecord.objects.select_related("employee", "cycle")
    serializer_class = PayrollRecordSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        # Admins can write, employees can read their own records
        if self.request and self.request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            return [IsAdminUser()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        # Employee self-views: filter by employee if nested
        employee = self.kwargs.get("employee_id") or self.request.query_params.get(
            "employee"
        )
        if employee:
            qs = qs.filter(employee_id=employee)
        return qs

    @action(detail=False, methods=["post"], permission_classes=[IsAdminUser])
    def run_cycle(self, request):
        """Trigger payroll generation for a given cycle.

        Body: { "cycle": "<cycle_id>" }
        Returns: summary counts
        """
        cycle_id = request.data.get("cycle")
        if not cycle_id:
            raise ValidationError({"cycle": "This field is required."})
        result = generate_payroll_for_cycle(cycle_id)
        return Response(result)


class PayrollReportViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    class PayrollReportRowSerializer(serializers.Serializer):
        employee_id = serializers.IntegerField()
        total_comp = serializers.DecimalField(max_digits=12, decimal_places=2)
        salary = serializers.DecimalField(max_digits=12, decimal_places=2)
        actual = serializers.DecimalField(max_digits=12, decimal_places=2)
        recurring = serializers.DecimalField(max_digits=12, decimal_places=2)
        one_off = serializers.DecimalField(max_digits=12, decimal_places=2)
        offset = serializers.DecimalField(max_digits=12, decimal_places=2)
        ot = serializers.DecimalField(max_digits=12, decimal_places=2)

    serializer_class = PayrollReportRowSerializer

    @extend_schema(tags=["Payroll • Reports"])
    def list(self, request):
        """Return a paginated payroll report (aggregated per employee) for a date range.

        Query params: start, end, page, page_size
        """
        start = request.query_params.get("start")
        end = request.query_params.get("end")
        qs = PayrollRecord.objects.filter(deleted_at__isnull=True)
        if start:
            qs = qs.filter(period_start__gte=start)
        if end:
            qs = qs.filter(period_end__lte=end)
        # Aggregate per employee
        agg = (
            qs.values("employee_id")
            .annotate(
                total_comp=Sum("total_compensation"),
                salary=Sum("salary"),
                actual=Sum("actual"),
                recurring=Sum("recurring"),
                one_off=Sum("one_off"),
                offset=Sum("offset"),
                ot=Sum("ot"),
            )
            .order_by("-total_comp")
        )
        # Simple pagination
        paginator = PageNumberPagination()
        rows: list[dict] = list(agg)
        paged = paginator.paginate_queryset(rows, request)
        serializer = self.serializer_class(paged, many=True)
        return paginator.get_paginated_response(serializer.data)


@extend_schema_view(
    list=extend_schema(tags=["Employees • Bank Details"]),
    retrieve=extend_schema(tags=["Employees • Bank Details"]),
    create=extend_schema(tags=["Employees • Bank Details"]),
    update=extend_schema(tags=["Employees • Bank Details"]),
    partial_update=extend_schema(tags=["Employees • Bank Details"]),
    destroy=extend_schema(tags=["Employees • Bank Details"]),
)
class BankDetailViewSet(viewsets.ModelViewSet):
    queryset = BankDetail.objects.select_related("employee")
    serializer_class = BankDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request and self.request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            return [IsAdminUser()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        employee = self.kwargs.get("employee_id") or self.request.query_params.get(
            "employee"
        )
        if employee:
            qs = qs.filter(employee_id=employee)
        return qs

    def get_serializer(self, *args, **kwargs):
        serializer = super().get_serializer(*args, **kwargs)
        if (
            self.request
            and self.request.method in {"POST", "PUT", "PATCH"}
            and self.kwargs.get("employee_id")
        ):
            target = getattr(serializer, "child", None) or serializer
            if hasattr(target, "fields") and "employee" in target.fields:
                target.fields["employee"].required = False
                target.fields["employee"].read_only = True
        return serializer

    def perform_create(self, serializer):
        # Bind employee automatically when using nested route; otherwise use payload
        employee_id = self.kwargs.get("employee_id")
        if employee_id:
            if not Employee.objects.filter(pk=employee_id).exists():
                msg = "Employee not found."
                raise NotFound(msg)
            serializer.save(employee_id=employee_id)
        else:
            serializer.save()


@extend_schema_view(
    list=extend_schema(tags=["Employees • Dependents"]),
    retrieve=extend_schema(tags=["Employees • Dependents"]),
    create=extend_schema(tags=["Employees • Dependents"]),
    update=extend_schema(tags=["Employees • Dependents"]),
    partial_update=extend_schema(tags=["Employees • Dependents"]),
    destroy=extend_schema(tags=["Employees • Dependents"]),
)
class DependentViewSet(viewsets.ModelViewSet):
    queryset = Dependent.objects.select_related("employee")
    serializer_class = DependentSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request and self.request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            return [IsAdminUser()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        employee = self.kwargs.get("employee_id") or self.request.query_params.get(
            "employee"
        )
        if employee:
            qs = qs.filter(employee_id=employee)
        return qs

    def get_serializer(self, *args, **kwargs):
        serializer = super().get_serializer(*args, **kwargs)
        if (
            self.request
            and self.request.method in {"POST", "PUT", "PATCH"}
            and self.kwargs.get("employee_id")
        ):
            target = getattr(serializer, "child", None) or serializer
            if hasattr(target, "fields") and "employee" in target.fields:
                target.fields["employee"].required = False
                target.fields["employee"].read_only = True
        return serializer

    def perform_create(self, serializer):
        # Bind employee automatically when using nested route; otherwise use payload
        employee_id = self.kwargs.get("employee_id")
        if employee_id:
            if not Employee.objects.filter(pk=employee_id).exists():
                msg = "Employee not found."
                raise NotFound(msg)
            serializer.save(employee_id=employee_id)
        else:
            serializer.save()
