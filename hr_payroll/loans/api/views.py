from dateutil.relativedelta import relativedelta
from django.utils import timezone
from rest_framework import permissions
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from hr_payroll.audit.utils import log_action
from hr_payroll.loans.api.serializers import LoanRequestSerializer
from hr_payroll.loans.models import LoanRepayment
from hr_payroll.loans.models import LoanRequest


class LoanRequestViewSet(viewsets.ModelViewSet):
    queryset = LoanRequest.objects.all()
    serializer_class = LoanRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff or user.is_superuser:
            return LoanRequest.objects.all()
        # Employees see only their own
        if hasattr(user, "employee"):
            return LoanRequest.objects.filter(employee=user.employee)
        return LoanRequest.objects.none()

    def perform_create(self, serializer):
        # Auto-link employee if not provided by admin
        if not self.request.user.is_staff and hasattr(self.request.user, "employee"):
            serializer.save(employee=self.request.user.employee)
        else:
            serializer.save()

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAdminUser])
    def approve(self, request, pk=None):
        loan = self.get_object()
        if loan.status != LoanRequest.Status.SUBMITTED:
            # Allow approving from draft for simplicity in MVP, or enforce submission flow
            pass

        loan.status = LoanRequest.Status.APPROVED
        loan.approved_by = request.user
        loan.approved_at = timezone.now()
        loan.save()

        # Generate Repayments
        start_date = timezone.now().date() + relativedelta(
            months=1
        )  # First payment next month
        repayments = []
        for i in range(loan.term_months):
            due_date = start_date + relativedelta(months=i)
            # Adjust last installment for rounding issues if needed, but using fixed installment for now
            repayments.append(
                LoanRepayment(
                    loan=loan,
                    due_date=due_date,
                    amount=loan.monthly_installment,
                    status=LoanRepayment.Status.PENDING,
                )
            )

        LoanRepayment.objects.bulk_create(repayments)

        # Log Action
        log_action(
            "loan.approve",
            actor=request.user,
            model_name="LoanRequest",
            record_id=loan.id,
            after={"status": "approved"},
        )

        return Response(self.get_serializer(loan).data)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAdminUser])
    def reject(self, request, pk=None):
        loan = self.get_object()
        reason = request.data.get("reason", "")
        loan.status = LoanRequest.Status.REJECTED
        loan.rejection_reason = reason
        loan.save()
        return Response(self.get_serializer(loan).data)
