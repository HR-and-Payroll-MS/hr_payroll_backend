from __future__ import annotations

import copy
from typing import Any

# NOTE: This structure intentionally mirrors the frontend's `initialPolicies`
# object (see: hr_payroll_front/src/Pages/HR_Manager/Policy/policiesSchema.js).
DEFAULT_POLICY_DOCUMENT: dict[str, Any] = {
    "general": {
        "companyName": "Example Co",
        "effectiveDate": "2025-01-01",
        "adminContact": "hr@example.com",
        "policyVersion": "v2.0",
    },
    "attendancePolicy": {
        "shiftTimes": [
            {"name": "Day Shift", "start": "09:00", "end": "17:00"},
            {"name": "Night Shift", "start": "18:00", "end": "02:00"},
        ],
        "gracePeriod": {
            "minutesAllowed": 15,
            "lateAfter": 15,
            "allowedOccurrencesPerMonth": 3,
            "penaltyRule": "Salary deduction after limit exceeded",
        },
        "lateEarlyRules": {
            "halfDayLateAfterMinutes": 120,
            "halfDayEarlyLeaveMinutes": 120,
            "acceptableLateMinutes": 15,
        },
        "absentRules": {
            "absentAfterMinutes": 240,
            "noClockInAbsent": True,
        },
        "workFromHome": {
            "allowedDaysPerMonth": 4,
            "approvalRequired": {
                "__type": "dropdown",
                "options": ["Yes", "No"],
                "value": "Yes",
            },
        },
        "overtimeRules": {
            "overtimeAllowed": {
                "__type": "dropdown",
                "options": ["Yes", "No"],
                "value": "Yes",
            },
            "overtimeApprovalRequired": {
                "__type": "dropdown",
                "options": ["Yes", "No"],
                "value": "Yes",
            },
            "minMinutes": 60,
            "maxDailyHours": 4,
            "maxWeeklyHours": 20,
        },
        "breakRules": {
            "lunchBreakAutoDeduct": {
                "__type": "dropdown",
                "options": ["Yes", "No"],
                "value": "Yes",
            },
            "lunchBreakMinutes": 60,
            "breakType": {
                "__type": "dropdown",
                "options": ["fixed", "flexible"],
                "value": "fixed",
            },
        },
        "attendanceCorrection": {
            "documentationRequired": {
                "__type": "dropdown",
                "options": ["Yes", "No"],
                "value": "Yes",
            },
            "approvalFlow": ["manager", "hr"],
        },
    },
    "leavePolicy": {
        "leaveTypes": [
            {"id": "annual", "name": "Annual Leave", "paid": True, "daysPerYear": 21},
            {"id": "sick", "name": "Sick Leave", "paid": True, "daysPerYear": 15},
            {"id": "casual", "name": "Casual Leave", "paid": True, "daysPerYear": 7},
        ],
        "accrualRules": {
            "monthlyAccrualDays": 1.75,
            "carryoverLimit": 12,
            "expiryMonths": 18,
            "proRataJoining": True,
        },
        "eligibilityRules": {
            "maternityMinServiceMonths": 3,
            "sabbaticalMinYears": 5,
            "casualLeaveProbation": False,
        },
        "encashmentRules": {
            "allowedAtSeparation": True,
            "maxEncashableDays": 30,
        },
        "documentationRules": {
            "sickLeaveCertificateAfterDays": 2,
            "bereavementRequired": True,
            "studyLeaveDocs": "Enrollment letter",
        },
        "approvalWorkflow": {
            "annualLeave": ["manager", "hr"],
            "sickLeave": ["hr"],
            "maternityLeave": ["hr"],
        },
    },
    "holidayPolicy": {
        "fixedHolidays": [
            {"date": "2025-01-01", "name": "New Year"},
            {"date": "2025-05-01", "name": "Labor Day"},
        ],
        "floatingHolidays": [
            {"name": "Religious Holiday", "rule": "Employee Choice (1/year)"}
        ],
        "companyHolidays": [{"date": "2025-12-31", "name": "Year End Closure"}],
        "holidayPayRules": {
            "holidayIsPaid": {
                "__type": "dropdown",
                "options": ["Yes", "No"],
                "value": "Yes",
            },
            "holidayOvertimeRate": 2.0,
        },
    },
    "shiftPolicy": {
        "workweek": ["Mon", "Tue", "Wed", "Thu", "Fri"],
        "weeklyOff": ["Sat", "Sun"],
        "shiftPatterns": [
            {"id": 1, "name": "Fixed Day Shift", "type": "fixed"},
            {"id": 2, "name": "Night Rotation", "type": "rotational"},
        ],
        "rotationRules": {"rotationEveryDays": 14, "nightShiftAllowance": 300},
    },
    "overtimePolicy": {
        "rates": {
            "standardRate": 1.5,
            "weekendRate": 2.0,
            "holidayRate": 2.0,
        },
        "compOff": {
            "allowed": True,
            "expireDays": 60,
        },
        "minOvertimeMinutes": 30,
        "approvalRequired": {
            "__type": "dropdown",
            "options": ["Yes", "No"],
            "value": "Yes",
        },
    },
    "probationPolicy": {
        "durationMonths": 3,
        "extensionMonths": 3,
        "noticePeriodDuringProbationDays": 15,
        "trainingRequired": True,
    },
    "expensePolicy": {
        "dailyPerDiem": 500,
        "travelLimits": {
            "flightClass": "Economy",
            "hotelPerNight": 2000,
        },
        "approvalWorkflow": ["manager", "finance"],
    },
    "loanPolicy": {
        "maxAmountMultiplier": 3,  # 3x Gross Salary
        "maxRepaymentMonths": 12,
        "interestRate": 0,
        "eligibilityMinServiceMonths": 6,
    },
    "terminationPolicy": {
        "noticePeriodDays": {
            "probation": 15,
            "confirmed": 30,
            "senior": 60,
        },
        "handoverChecklist": ["Laptop", "ID Card", "Keys"],
    },
    "disciplinaryPolicy": {
        "warningRules": {
            "firstWarning": "Verbal Warning",
            "secondWarning": "Written Warning",
            "thirdWarning": "Final Warning / Suspension",
        },
        "penalties": {
            "repeatedLatePenalty": "Deduction",
            "absencePenalty": "Warning Letter",
        },
        "escalation": {"steps": ["manager", "hr", "director"]},
    },
    "jobStructurePolicy": {
        "jobLevels": [
            "Intern",
            "Junior",
            "Mid",
            "Senior",
            "Lead",
            "Manager",
            "Director",
        ],
        "departments": [
            "HR",
            "Finance",
            "Engineering",
            "Operations",
            "Sales",
            "Marketing",
        ],
        "promotionRules": {
            "minimumMonthsPerLevel": 12,
            "requiredPerformanceRating": "Exceeds Expectations",
        },
    },
    "salaryStructurePolicy": {
        "baseSalaryTemplate": {"gradeA": 30000, "gradeB": 20000, "gradeC": 15000},
        "allowances": [
            {"name": "Transport", "value": 1500},
            {"name": "Housing", "value": 3000},
            {"name": "Internet", "value": 500},
        ],
        "deductions": {
            "pensionPercent": 8,
            "taxBracket": [
                {"min": 0, "max": 10000, "rate": 0, "appliedfor": "All"},
                {"min": 10001, "max": 25000, "rate": 10, "appliedfor": "All"},
                {"min": 25001, "max": 50000, "rate": 20, "appliedfor": "All"},
            ],
        },
    },
}


def get_default_policy_document() -> dict[str, Any]:
    """Return a deep copy of the default policy document.

    We return a deep copy to avoid accidental runtime mutation.
    """

    return copy.deepcopy(DEFAULT_POLICY_DOCUMENT)
