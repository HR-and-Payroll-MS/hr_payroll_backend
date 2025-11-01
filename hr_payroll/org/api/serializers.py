from rest_framework import serializers

from hr_payroll.org.models import Department


class DepartmentSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()

    class Meta:
        model = Department
        fields = ["id", "name", "description", "location", "budget_code"]

    def get_id(self, obj: Department) -> str:
        return str(obj.pk)
