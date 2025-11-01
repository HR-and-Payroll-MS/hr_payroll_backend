from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import extend_schema_view
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAdminUser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from hr_payroll.payroll.models import Compensation
from hr_payroll.payroll.models import SalaryComponent

from .serializers import CompensationSerializer
from .serializers import SalaryComponentSerializer


@extend_schema_view(
    list=extend_schema(tags=["Payroll"]),
    retrieve=extend_schema(tags=["Payroll"]),
    create=extend_schema(tags=["Payroll"]),
    update=extend_schema(tags=["Payroll"]),
    partial_update=extend_schema(tags=["Payroll"]),
    destroy=extend_schema(tags=["Payroll"]),
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
            try:
                instance = serializer.save(employee_id=employee_id)
            except Exception:  # If FK invalid, return a clean 404
                from rest_framework.exceptions import NotFound

                raise NotFound("Employee not found.")
        else:
            instance = serializer.save()

    @action(
        detail=True,
        methods=["post"],
        url_path="apply-to-employee",
        permission_classes=[IsAdminUser],
    )
    def apply_to_employee(self, request, pk=None):
        """
        Clone this compensation's components into a NEW compensation for the target employee.
        Body: { "employee": "<employee_id>" }
        Returns the created Compensation payload.
        """
        from rest_framework.exceptions import NotFound
        from rest_framework.exceptions import ValidationError

        target_employee = request.data.get("employee")
        if not target_employee:
            raise ValidationError({"employee": "This field is required."})

        try:
            source = self.get_queryset().get(pk=pk)
        except Compensation.DoesNotExist:
            raise NotFound("Compensation not found.")

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
    list=extend_schema(tags=["Payroll"]),
    retrieve=extend_schema(tags=["Payroll"]),
    create=extend_schema(tags=["Payroll"]),
    update=extend_schema(tags=["Payroll"]),
    partial_update=extend_schema(tags=["Payroll"]),
    destroy=extend_schema(tags=["Payroll"]),
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
        # Enforce double nesting and ownership: the compensation must belong to the employee
        comp_id = self.kwargs.get("compensation_id")
        emp_id = self.kwargs.get("employee_id")
        if comp_id and emp_id:
            from rest_framework.exceptions import NotFound

            try:
                comp = Compensation.objects.get(pk=comp_id, employee_id=emp_id)
            except Compensation.DoesNotExist:
                raise NotFound("Compensation not found for this employee.")
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
