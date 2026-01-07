from django.utils import timezone
from rest_framework import serializers

from hr_payroll.loans.models import LoanRepayment
from hr_payroll.loans.models import LoanRequest
from hr_payroll.policies import get_policy_document


class LoanRepaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoanRepayment
        fields = ["id", "due_date", "amount", "status", "payroll_slip"]
        read_only_fields = ["status", "payroll_slip"]


class LoanRequestSerializer(serializers.ModelSerializer):
    repayments = LoanRepaymentSerializer(many=True, read_only=True)
    employee_name = serializers.CharField(
        source="employee.user.get_full_name", read_only=True
    )

    class Meta:
        model = LoanRequest
        fields = [
            "id",
            "employee",
            "employee_name",
            "amount",
            "term_months",
            "interest_rate",
            "monthly_installment",
            "reason",
            "status",
            "approved_by",
            "approved_at",
            "rejection_reason",
            "created_at",
            "repayments",
        ]
        read_only_fields = [
            "interest_rate",
            "monthly_installment",
            "status",
            "approved_by",
            "approved_at",
            "rejection_reason",
        ]

    def validate(self, data):
        self.context.get("request")
        employee = data.get("employee")
        amount = data.get("amount")
        term_months = data.get("term_months")

        # 1. Get Policy
        # Assuming org_id 1 or from employee's org. For now defaulting to 1 or active context.
        org_id = employee.department.organization_id if employee.department else 1
        policy_doc = get_policy_document(org_id=org_id)
        loan_policy = policy_doc.get("loanPolicy", {})

        # 2. Check Eligibility (Tenure)
        min_service = loan_policy.get("eligibilityMinServiceMonths", 0)
        if min_service > 0:
            tenure = timezone.now().date() - employee.joining_date
            months_service = tenure.days // 30  # Rough estimate
            if months_service < min_service:
                msg = f"Employee must have completed {min_service} months of service."
                raise serializers.ValidationError(msg)

        # 3. Check Max Amount
        salary_structure = getattr(employee, "salary_structure", None)
        base_salary = salary_structure.base_salary if salary_structure else 0
        multiplier = loan_policy.get("maxAmountMultiplier", 0)

        if multiplier > 0 and base_salary > 0:
            max_amount = base_salary * multiplier
            if amount > max_amount:
                msg = (
                    f"Loan amount exceeds limit ({multiplier}x Salary = {max_amount})."
                )
                raise serializers.ValidationError(msg)

        # 4. Check Term
        max_term = loan_policy.get("maxRepaymentMonths", 0)
        if max_term > 0 and term_months > max_term:
            msg = f"Repayment term cannot exceed {max_term} months."
            raise serializers.ValidationError(msg)

        return data

    def create(self, validated_data):
        # Auto-set interest rate from policy
        employee = validated_data.get("employee")
        org_id = employee.department.organization_id if employee.department else 1
        policy_doc = get_policy_document(org_id=org_id)
        loan_policy = policy_doc.get("loanPolicy", {})

        interest_rate = loan_policy.get("interestRate", 0)
        validated_data["interest_rate"] = interest_rate

        amount = validated_data["amount"]
        months = validated_data["term_months"]

        if interest_rate > 0:
            interest = amount * (interest_rate / 100) * (months / 12)
            total_payable = amount + interest
        else:
            total_payable = amount

        validated_data["monthly_installment"] = total_payable / months

        return super().create(validated_data)
