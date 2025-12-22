from __future__ import annotations

import re
from typing import Any

from django.utils.text import slugify
from rest_framework import serializers

from hr_payroll.efficiency.models import EfficiencyEvaluation
from hr_payroll.efficiency.models import EfficiencyTemplate

_ALLOWED_METRIC_TYPES = {"number", "dropdown"}
_ALLOWED_FEEDBACK_TYPES = {"text", "textarea", "dropdown"}


def _schema_check_is_object(v: dict) -> None:
    if not isinstance(v, dict):
        msg = "schema must be an object"
        raise serializers.ValidationError(msg)


def _schema_extract_lists(v: dict) -> tuple[list, list]:
    pm_list = v.get("performanceMetrics") or []
    fs_list = v.get("feedbackSections") or []
    if not isinstance(pm_list, list) or not isinstance(fs_list, list):
        msg = "schema.performanceMetrics and schema.feedbackSections must be arrays"
        raise serializers.ValidationError(msg)
    return pm_list, fs_list


def _schema_check_title(v: dict) -> None:
    title = v.get("title")
    if not title or not isinstance(title, str):
        msg = "schema.title must be a non-empty string"
        raise serializers.ValidationError(msg)


def _schema_ensure_field_id(it: dict, prefix: str) -> None:
    if "id" not in it:
        it["id"] = slugify(str(it.get("name") or f"{prefix}-field"))


def _schema_validate_metric(it: dict) -> None:
    if not isinstance(it, dict):
        msg = "performanceMetrics items must be objects"
        raise serializers.ValidationError(msg)
    _schema_ensure_field_id(it, "metric")
    t = str(it.get("type") or "").lower()
    if t not in _ALLOWED_METRIC_TYPES:
        msg = f"Unsupported metric type: {t}"
        raise serializers.ValidationError(msg)
    w = it.get("weight")
    if t == "number":
        if w is None or float(w) < 0:
            msg = "number metric must have non-negative weight"
            raise serializers.ValidationError(msg)
    if t == "dropdown":
        opts = it.get("options") or []
        if not opts or not isinstance(opts, list):
            msg = "dropdown metric must have options"
            raise serializers.ValidationError(msg)
        for opt in opts:
            if not isinstance(opt, dict):
                msg = "dropdown option must be object"
                raise serializers.ValidationError(msg)
            if "point" not in opt:
                msg = "dropdown option missing 'point'"
                raise serializers.ValidationError(msg)


def _schema_validate_feedback(it: dict) -> None:
    if not isinstance(it, dict):
        msg = "feedbackSections items must be objects"
        raise serializers.ValidationError(msg)
    _schema_ensure_field_id(it, "feedback")
    t = str(it.get("type") or "").lower()
    if t not in _ALLOWED_FEEDBACK_TYPES:
        msg = f"Unsupported feedback type: {t}"
        raise serializers.ValidationError(msg)


class EfficiencyTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = EfficiencyTemplate
        fields = [
            "id",
            "org_id",
            "department",
            "title",
            "schema",
            "version",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ("created_at", "updated_at")

    def validate_schema(self, value: dict) -> dict:
        _schema_check_is_object(value)
        _schema_check_title(value)
        pm, fs = _schema_extract_lists(value)
        for it in pm:
            _schema_validate_metric(it)
        for it in fs:
            _schema_validate_feedback(it)
        return value


class EfficiencyEvaluationSerializer(serializers.ModelSerializer):
    class Meta:
        model = EfficiencyEvaluation
        fields = [
            "id",
            "template",
            "employee",
            "department",
            "evaluator",
            "data",
            "total_achieved",
            "total_possible",
            "total_efficiency",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = (
            "total_achieved",
            "total_possible",
            "total_efficiency",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs: dict) -> dict:  # noqa: C901, PLR0912, PLR0915
        tpl: EfficiencyTemplate = attrs.get("template") or getattr(
            self.instance, "template", None
        )
        data: dict = attrs.get("data") or {}
        if not tpl:
            raise serializers.ValidationError({"template": "Template is required"})
        schema = tpl.schema or {}
        pm = schema.get("performanceMetrics") or []
        answers: dict[str, Any] = {}
        # Accept either concise answers dict or FE 'report' style
        if isinstance(data, dict):
            if "answers" in data and isinstance(data["answers"], dict):
                answers = data["answers"]
            elif "performanceMetrics" in data and isinstance(
                data["performanceMetrics"], list
            ):
                for item in data["performanceMetrics"]:
                    fid = item.get("id")
                    sel = item.get("selected")
                    if fid:
                        answers[str(fid)] = sel
                # merge feedback
                for item in data.get("feedback", []):
                    fid = item.get("id")
                    val = item.get("value")
                    if fid:
                        answers[str(fid)] = val
        # Compute totals
        total_achieved = 0.0
        total_possible = 0.0
        per_metric = []
        for field in pm:
            fid = str(field.get("id"))
            ftype = str(field.get("type") or "").lower()
            weight = float(field.get("weight") or 0)
            answer = answers.get(fid)
            field_possible = 0.0
            field_achieved = 0.0
            if ftype == "number":
                field_possible = max(weight, 0)
                try:
                    field_achieved = min(float(answer or 0), field_possible)
                except (ValueError, TypeError):
                    field_achieved = 0.0
            elif ftype == "dropdown":
                opts = field.get("options") or []
                # possible is max option point
                points = [float(o.get("point") or 0) for o in opts]
                field_possible = max(points) if points else 0.0
                # achieved: extract number from string or match by label
                val = str(answer) if answer is not None else ""
                got = None

                m = re.search(r"(\d+(?:\.\d+)?)", val)
                if m:
                    try:
                        got = float(m.group(1))
                    except ValueError:
                        got = None
                if got is None:
                    # match by label equality
                    for o in opts:
                        if str(o.get("label")) == val:
                            got = float(o.get("point") or 0)
                            break
                field_achieved = float(got or 0)
            total_achieved += field_achieved
            total_possible += field_possible
            per_metric.append(
                {
                    "id": fid,
                    "name": field.get("name"),
                    "achieved": field_achieved,
                    "possible": field_possible,
                }
            )
        total_efficiency = (
            (total_achieved / total_possible * 100.0) if total_possible > 0 else 0.0
        )
        # Enrich data with server-side summary
        data.setdefault("summary", {})
        data["summary"].update(
            {
                "totalAchieved": total_achieved,
                "totalPossible": total_possible,
                "perMetric": per_metric,
            }
        )
        data.setdefault("title", schema.get("title"))
        attrs["data"] = data
        attrs["total_achieved"] = total_achieved
        attrs["total_possible"] = total_possible
        attrs["total_efficiency"] = float(round(total_efficiency, 2))
        # Default department/evaluator if not provided
        emp = attrs.get("employee")
        if emp is not None and attrs.get("department") is None:
            attrs["department"] = emp.department
        req = self.context.get("request")
        if req is not None and attrs.get("evaluator") is None:
            attrs["evaluator"] = getattr(req.user, "employee", None)
        return attrs
