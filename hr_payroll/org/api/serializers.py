from rest_framework import serializers

from hr_payroll.employees.models import Employee
from hr_payroll.org.models import Department
from hr_payroll.org.models import OrgChartNode


class DepartmentSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()

    class Meta:
        model = Department
        fields = ["id", "name", "description", "location", "budget_code"]

    def get_id(self, obj: Department) -> str:
        return str(obj.pk)


class OrgChartNodeSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    occupant = serializers.PrimaryKeyRelatedField(
        queryset=Employee.objects.all(), allow_null=True, required=False
    )
    parent = serializers.PrimaryKeyRelatedField(
        queryset=OrgChartNode.objects.all(), allow_null=True, required=False
    )
    occupant_name = serializers.SerializerMethodField()
    occupant_photo = serializers.SerializerMethodField()

    class Meta:
        model = OrgChartNode
        fields = [
            "id",
            "title",
            "parent",
            "order",
            "occupant",
            "occupant_name",
            "occupant_photo",
        ]

    def get_id(self, obj: OrgChartNode) -> str:
        return str(obj.pk)

    def get__request(self):
        if isinstance(self.context, dict):
            return self.context.get("request")
        return None

    def get_occupant_name(self, obj: OrgChartNode) -> str:
        emp = getattr(obj, "occupant", None)
        if not emp:
            return ""
        user = getattr(emp, "user", None)
        return getattr(user, "name", "") or ""

    def get_occupant_photo(self, obj: OrgChartNode) -> str:
        emp = getattr(obj, "occupant", None)
        if not emp or not getattr(emp, "photo", None):
            return ""
        url = getattr(emp.photo, "url", "")
        if not url:
            return ""
        request = self.get__request()
        return request.build_absolute_uri(url) if request else url


class OrgChartNodeTreeSerializer(OrgChartNodeSerializer):
    children = serializers.SerializerMethodField()

    class Meta(OrgChartNodeSerializer.Meta):
        fields = [*OrgChartNodeSerializer.Meta.fields, "children"]

    def get_children(self, obj: OrgChartNode):
        children = getattr(obj, "children_cached", None)
        # Fallback to actual relation if pre-annotated list missing
        if children is None:
            qs = obj.children.select_related("occupant").order_by("order", "id")
            return OrgChartNodeTreeSerializer(qs, many=True, context=self.context).data
        return OrgChartNodeTreeSerializer(
            children, many=True, context=self.context
        ).data
