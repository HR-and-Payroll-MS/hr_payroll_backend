from django.utils import timezone
from rest_framework import permissions
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from hr_payroll.audit.utils import log_action
from hr_payroll.expenses.api.serializers import ExpenseRequestSerializer
from hr_payroll.expenses.models import ExpenseRequest


class ExpenseRequestViewSet(viewsets.ModelViewSet):
    queryset = ExpenseRequest.objects.all()
    serializer_class = ExpenseRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return ExpenseRequest.objects.all()
        if hasattr(user, "employee"):
            return ExpenseRequest.objects.filter(employee=user.employee)
        return ExpenseRequest.objects.none()

    def perform_create(self, serializer):
        if not self.request.user.is_staff and hasattr(self.request.user, "employee"):
            serializer.save(employee=self.request.user.employee)
        else:
            serializer.save()

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAdminUser])
    def approve(self, request, pk=None):
        expense = self.get_object()
        expense.status = ExpenseRequest.Status.APPROVED
        expense.approved_by = request.user
        expense.approved_at = timezone.now()
        expense.save()

        log_action(
            "expense.approve",
            actor=request.user,
            model_name="ExpenseRequest",
            record_id=expense.id,
            after={"status": "approved"},
        )
        return Response(self.get_serializer(expense).data)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAdminUser])
    def reject(self, request, pk=None):
        expense = self.get_object()
        reason = request.data.get("reason", "")
        expense.status = ExpenseRequest.Status.REJECTED
        expense.rejection_reason = reason
        expense.save()
        return Response(self.get_serializer(expense).data)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAdminUser])
    def reimburse(self, request, pk=None):
        expense = self.get_object()
        if expense.status != ExpenseRequest.Status.APPROVED:
            return Response(
                {"detail": "Only approved expenses can be reimbursed."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        expense.status = ExpenseRequest.Status.REIMBURSED
        expense.save()
        return Response(self.get_serializer(expense).data)
