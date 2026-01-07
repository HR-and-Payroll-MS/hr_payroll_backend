from rest_framework import serializers

from hr_payroll.expenses.models import ExpenseRequest
from hr_payroll.policies import get_policy_document


class ExpenseRequestSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(
        source="employee.user.get_full_name", read_only=True
    )

    class Meta:
        model = ExpenseRequest
        fields = [
            "id",
            "employee",
            "employee_name",
            "category",
            "amount",
            "description",
            "receipt",
            "expense_date",
            "status",
            "approved_by",
            "approved_at",
            "rejection_reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["status", "approved_by", "approved_at", "rejection_reason"]

    def validate(self, data):
        employee = data.get("employee")
        amount = data.get("amount")
        receipt = data.get("receipt")

        # Get Policy
        org_id = employee.department.organization_id if employee.department else 1
        policy_doc = get_policy_document(org_id=org_id)
        expense_policy = policy_doc.get("expensePolicy", {})

        # Check if receipt is required
        receipt_threshold = expense_policy.get("travelLimits", {}).get(
            "receiptRequiredAbove", 0
        )
        if receipt_threshold > 0 and amount and amount > receipt_threshold:
            if not receipt:
                msg = f"Receipt is required for expenses above {receipt_threshold}."
                raise serializers.ValidationError(msg)

        # Check category limits
        categories = expense_policy.get("categories", [])
        category = data.get("category")
        if isinstance(categories, list):
            for cat_def in categories:
                if (
                    isinstance(cat_def, dict)
                    and cat_def.get("name", "").lower() == category
                ):
                    limit = cat_def.get("limit", 0)
                    if limit > 0 and amount > limit:
                        msg = f"Expense exceeds category limit of {limit}."
                        raise serializers.ValidationError(msg)
                    break

        return data
