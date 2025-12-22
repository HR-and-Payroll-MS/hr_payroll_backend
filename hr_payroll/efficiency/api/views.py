from __future__ import annotations

import logging

from drf_spectacular.utils import extend_schema
from drf_spectacular.utils import extend_schema_view
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from hr_payroll.audit.utils import log_action
from hr_payroll.efficiency.api.serializers import EfficiencyEvaluationSerializer
from hr_payroll.efficiency.api.serializers import EfficiencyTemplateSerializer
from hr_payroll.efficiency.models import EfficiencyEvaluation
from hr_payroll.efficiency.models import EfficiencyTemplate
from hr_payroll.employees.api.permissions import IsAdminOrHROrLineManagerScopedWrite
from hr_payroll.employees.api.permissions import IsAdminOrManagerOnly
from hr_payroll.employees.api.permissions import _user_in_groups

logger = logging.getLogger(__name__)


@extend_schema_view(
    list=extend_schema(summary="List efficiency templates"),
    retrieve=extend_schema(summary="Get a template"),
    create=extend_schema(summary="Create a template"),
    partial_update=extend_schema(summary="Update a template"),
    destroy=extend_schema(summary="Delete a template"),
)
class EfficiencyTemplateViewSet(viewsets.ModelViewSet):
    queryset = EfficiencyTemplate.objects.filter(is_active=True)
    serializer_class = EfficiencyTemplateSerializer
    permission_classes = [IsAuthenticated, IsAdminOrManagerOnly]

    def perform_create(self, serializer):
        obj = serializer.save(created_by=getattr(self.request.user, "employee", None))
        log_action(
            "efficiency.template.create",
            actor=getattr(self.request, "user", None),
            model_name="EfficiencyTemplate",
            record_id=obj.id,
            after={"title": obj.title},
        )

    def perform_update(self, serializer):
        obj = serializer.save()
        log_action(
            "efficiency.template.update",
            actor=getattr(self.request, "user", None),
            model_name="EfficiencyTemplate",
            record_id=obj.id,
            after={"title": obj.title},
        )

    def perform_destroy(self, instance):
        log_action(
            "efficiency.template.delete",
            actor=getattr(self.request, "user", None),
            model_name="EfficiencyTemplate",
            record_id=instance.id,
            before={"title": instance.title},
        )
        return super().perform_destroy(instance)

    @action(detail=False, methods=["get"], url_path="schema")
    def get_schema(self, request):
        """Return the active template schema.

        Response is a plain JSON object with keys like:
        title, performanceMetrics, feedbackSections.
        """
        tpl = self.get_queryset().first()
        if not tpl:
            return Response({}, status=200)
        return Response(tpl.schema or {}, status=200)

    @action(detail=False, methods=["put"], url_path="schema-set")
    def put_schema(self, request):
        """Replace the active template schema with the provided JSON.

        Accepts exact frontend JSON and stores it as-is; returns the same JSON.
        """
        tpl = self.get_queryset().first()
        title = (request.data or {}).get("title") or (
            tpl.title if tpl else "Efficiency Template"
        )
        ser = self.get_serializer(
            tpl,
            data={
                "title": title,
                "schema": request.data,
            },
            partial=True,
        )
        ser.is_valid(raise_exception=True)
        obj = ser.save()
        log_action(
            "efficiency.template.schema.update",
            actor=getattr(request, "user", None),
            model_name="EfficiencyTemplate",
            record_id=obj.id,
            after={"title": obj.title},
        )
        return Response(obj.schema or {}, status=200)


@extend_schema_view(
    list=extend_schema(summary="List evaluations"),
    retrieve=extend_schema(summary="Get an evaluation"),
    create=extend_schema(summary="Submit evaluation"),
    partial_update=extend_schema(summary="Update evaluation status/body"),
)
class EfficiencyEvaluationViewSet(viewsets.ModelViewSet):
    queryset = EfficiencyEvaluation.objects.all().select_related(
        "employee", "department", "template"
    )
    serializer_class = EfficiencyEvaluationSerializer
    permission_classes = [IsAuthenticated, IsAdminOrHROrLineManagerScopedWrite]

    def get_queryset(self):
        qs = super().get_queryset()
        # Scope:
        # - Employees: their own
        # - Line managers: limited to their department
        # - Admin/Manager: all
        # - Superuser: all
        user = getattr(self.request, "user", None)
        emp = getattr(user, "employee", None)
        if not user or not getattr(user, "is_authenticated", False):
            return qs.none()
        if getattr(user, "is_superuser", False):
            return qs
        # Admin/Manager groups can view all
        if _user_in_groups(user, ["Admin", "Manager"]):
            return qs
        # Line Manager: limit to their department
        if _user_in_groups(user, ["Line Manager"]) and emp and emp.department_id:
            return qs.filter(department_id=emp.department_id)
        # Otherwise: just own
        if emp:
            return qs.filter(employee_id=emp.id)
        return qs.none()

    def perform_create(self, serializer):
        obj = serializer.save()
        log_action(
            "efficiency.evaluation.create",
            actor=getattr(self.request, "user", None),
            model_name="EfficiencyEvaluation",
            record_id=obj.id,
            after={
                "template_id": obj.template_id,
                "employee_id": obj.employee_id,
                "total_efficiency": obj.total_efficiency,
            },
        )

    @action(detail=False, methods=["post"], url_path="submit")
    def submit(self, request):
        """Accept FE evaluation payload and return the same JSON with computed summary.

        Request body should contain either:
        - data.answers: { fieldId: value }
        - or data.performanceMetrics [{id, selected}] and data.feedback [{id, value}]
        Additionally requires template and employee IDs.
        """
        payload = request.data.copy()

        # Normalize common FE payloads to the serializer shape
        tpl_id = payload.get("template") or payload.get("template_id")
        if not tpl_id:
            tpl = EfficiencyTemplate.objects.filter(is_active=True).first()
            if tpl:
                payload["template"] = tpl.id
        else:
            payload["template"] = tpl_id

        emp_id = payload.get("employee") or payload.get("employee_id")
        if not emp_id and getattr(request.user, "employee", None):
            payload["employee"] = request.user.employee.id
        elif emp_id:
            payload["employee"] = emp_id

        if "data" not in payload:
            data_block = {}
            if payload.get("performanceMetrics"):
                data_block["performanceMetrics"] = payload.get("performanceMetrics")
            if payload.get("feedback"):
                data_block["feedback"] = payload.get("feedback")
            if data_block:
                payload["data"] = data_block

        logger.info("Efficiency submit payload: %s", payload)
        serializer = self.get_serializer(data=payload)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception:
            logger.exception("Efficiency submit validation failed")
            raise

        obj = serializer.save()
        # Return only the plain JSON data structure back to the FE
        return Response(obj.data or {}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"], url_path=r"employee/(?P<employee_id>[^/.]+)")
    def list_by_employee(self, request, employee_id: str):
        """List evaluations for a specific employee respecting role scoping."""
        qs = self.get_queryset().filter(employee_id=employee_id)
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(
        detail=False, methods=["get"], url_path=r"department/(?P<department_id>[^/.]+)"
    )
    def list_by_department(self, request, department_id: str):
        """List evaluations for a department.

        HR/manager: all; line manager: limited; employees: none.
        """
        qs = self.get_queryset().filter(department_id=department_id)
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(
        detail=False,
        methods=["get"],
        url_path="reports/department/(?P<department_id>[^/.]+)",
    )
    def department_report(self, request, department_id: str):
        qs = self.get_queryset().filter(department_id=department_id)
        # Aggregate simple stats
        total = qs.count()
        avg_eff = qs.aggregate_avg = (
            sum(e.total_efficiency for e in qs) / total if total else 0.0
        )
        return Response(
            {
                "department_id": int(department_id),
                "total": total,
                "averageEfficiency": round(avg_eff, 2),
            }
        )
