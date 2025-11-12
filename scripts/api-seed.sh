#!/usr/bin/env bash
#
# API Seed & End‑to‑End Test Script for hr_payroll (v1)
#
# What this does
# - Logs in (body-based JWT) and exports a Bearer token
# - Creates a Department
# - Onboards an existing User as an Employee
# - Adds Compensation and Salary Components (base, recurring, one-off, offset)
# - Creates Attendance records (incl. a paid-time adjustment → overtime)
# - Creates a Payroll Cycle (eligibility=list) and runs payroll
# - Fetches Payroll Records and a Payroll Report
# - Adds Bank Details and a Dependent to the employee
#
# Requirements
# - bash, curl, jq
# - You must already have a valid user (e.g., superuser) with known credentials.
# - That user must be able to create and manage resources (Admin/Manager).
#
# Notes
# - Default BASE points to local dev server; change as needed.
# - Script is idempotent-ish for a fresh DB; if you re-run, unique constraints
#   (e.g., Employee.employee_id) may require you to tweak values.
# - For cookie-based auth (HttpOnly cookies) see the section at the bottom.
#
set -euo pipefail
IFS=$'\n\t'

# ---------- Configurable inputs ----------
: "${BASE:=http://localhost:8000}"          # Base URL for the API
: "${USERNAME:=admin}"                      # Existing username with permissions
: "${PASSWORD:=admin}"                      # Password for that user

# ---------- Helpers ----------
header() { echo; echo "# ==== $* ====\n"; }
req() {
  local method="$1"; shift
  local url="$1"; shift
  curl -sS -X "$method" "$url" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${ACCESS:-}" "$@"
}

# ---------- 1) Authenticate (body-based JWT) ----------
header "1) Authenticate (JWT)"
ACCESS=$(curl -sS -X POST "$BASE/api/v1/auth/djoser/jwt/create/" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}" | jq -r .access)
if [[ -z "${ACCESS:-}" || "${ACCESS}" == "null" ]]; then
  echo "ERROR: Login failed. Check BASE/USERNAME/PASSWORD and try again." >&2
  exit 1
fi
export ACCESS
echo "Access token acquired."

# Optional: verify token
req POST "$BASE/api/v1/auth/djoser/jwt/verify/" -d "{\"token\":\"$ACCESS\"}" >/dev/null

# Who am I?
header "Who am I? (users/me)"
req GET "$BASE/api/v1/users/me/" | jq .

# ---------- 2) Department ----------
header "2) Create a Department"
DEPT_NAME="Engineering $(date +%s)"
DEPT=$(req POST "$BASE/api/v1/departments/" \
  -d "{\n    \"name\": \"$DEPT_NAME\",\n    \"description\": \"Core product engineering\",\n    \"location\": \"HQ\",\n    \"budget_code\": \"ENG-100\"\n  }")
DEPT_ID=$(echo "$DEPT" | jq -r .id)
echo "Department created: id=$DEPT_ID name=$DEPT_NAME"

# ---------- 3) Onboard an existing user as Employee ----------
# We need a User without an Employee. List candidates (Admin/Manager only).
header "3) Find a user without an Employee (candidates)"
CANDS=$(req GET "$BASE/api/v1/employees/onboard/candidates?limit=5")
echo "$CANDS" | jq .
USER_ID=$(echo "$CANDS" | jq -r '.[0].id')
if [[ -z "${USER_ID:-}" || "${USER_ID}" == "null" ]]; then
  echo "ERROR: No candidate users found. Create a user first (e.g., via admin)." >&2
  exit 1
fi
echo "Using candidate user_id=$USER_ID"

# Onboard
header "Onboard user → Employee"
EMP=$(req POST "$BASE/api/v1/employees/onboard/existing/" \
  -d "{\n    \"user\": $USER_ID,\n    \"department_id\": $DEPT_ID,\n    \"title\": \"Software Engineer\",\n    \"employee_id\": \"E-$(date +%Y%m%d-%H%M%S)\"\n  }")
echo "$EMP" | jq .
EMP_ID=$(echo "$EMP" | jq -r .id)
echo "Employee created: id=$EMP_ID"

# Optional: create Job History and Contract entries
header "Employee Job History & Contract"
req POST "$BASE/api/v1/employees/$EMP_ID/job-histories/" \
  -d '{"effective_date":"'"$(date -I)'"","job_title":"Software Engineer","position_type":"IC","employment_type":"fulltime"}' | jq .
req POST "$BASE/api/v1/employees/$EMP_ID/contracts/" \
  -d '{"contract_number":"CN-001","contract_name":"Full-time Offer","contract_type":"permanent","start_date":"'"$(date -I)'""}' | jq .

# ---------- 4) Compensation + Salary Components ----------
header "4) Create a Compensation for the employee"
COMP=$(req POST "$BASE/api/v1/employees/$EMP_ID/compensations/" -d '{}')
COMP_ID=$(echo "$COMP" | jq -r .id)
echo "Compensation created: id=$COMP_ID"

echo "Add salary components (base, recurring, one-off, offset)"
req POST "$BASE/api/v1/employees/$EMP_ID/compensations/$COMP_ID/salary-components/" \
  -d '{"kind":"base","amount":"3000.00","label":"Base Salary"}' | jq .
req POST "$BASE/api/v1/employees/$EMP_ID/compensations/$COMP_ID/salary-components/" \
  -d '{"kind":"recurring","amount":"200.00","label":"Allowance"}' | jq .
req POST "$BASE/api/v1/employees/$EMP_ID/compensations/$COMP_ID/salary-components/" \
  -d '{"kind":"one_off","amount":"150.00","label":"Joining Bonus"}' | jq .
req POST "$BASE/api/v1/employees/$EMP_ID/compensations/$COMP_ID/salary-components/" \
  -d '{"kind":"offset","amount":"50.00","label":"Equipment Deduction"}' | jq .

# ---------- 5) Attendance ----------
header "5) Create Attendance records"
# Day 1: Full day (no OT)
ATT1=$(req POST "$BASE/api/v1/attendances/" \
  -d "{\n    \"employee\": $EMP_ID,\n    \"date\": \"$(date -I)\",\n    \"clock_in\": \"$(date -I)T09:00:00Z\",\n    \"clock_in_location\": \"HQ\",\n    \"clock_out\": \"$(date -I)T17:00:00Z\",\n    \"clock_out_location\": \"HQ\",\n    \"work_schedule_hours\": 8,\n    \"paid_time\": \"08:00:00\"\n  }")
ATT1_ID=$(echo "$ATT1" | jq -r .id)
echo "Attendance 1: id=$ATT1_ID"

# Day 2: Overtime day (adjust paid_time to 9h to populate overtime_seconds)
ATT2_DATE=$(date -I -d "+1 day")
ATT2=$(req POST "$BASE/api/v1/attendances/" \
  -d "{\n    \"employee\": $EMP_ID,\n    \"date\": \"$ATT2_DATE\",\n    \"clock_in\": \"${ATT2_DATE}T09:00:00Z\",\n    \"clock_in_location\": \"HQ\",\n    \"clock_out\": \"${ATT2_DATE}T18:00:00Z\",\n    \"clock_out_location\": \"HQ\",\n    \"work_schedule_hours\": 8,\n    \"paid_time\": \"08:00:00\"\n  }")
ATT2_ID=$(echo "$ATT2" | jq -r .id)
echo "Attendance 2: id=$ATT2_ID"

# Adjust paid time to 9 hours -> sets status=PENDING and overtime_seconds
req POST "$BASE/api/v1/attendances/$ATT2_ID/adjust-paid-time/" \
  -d '{"paid_time":"09:00:00","notes":"Overtime due to release"}' | jq .
# Approve the adjusted attendance (so it counts as approved work)
req POST "$BASE/api/v1/attendances/$ATT2_ID/approve/" | jq .

# Optional: summaries
header "Attendance summaries"
req GET "$BASE/api/v1/attendances/my/summary/" | jq .
req GET "$BASE/api/v1/attendances/team/summary/" | jq .

# ---------- 6) Payroll Cycle ----------
header "6) Create a Payroll Cycle (eligibility=list)"
START=$(date -I -d "-1 day")
END=$(date -I -d "+7 day")
CYCLE=$(req POST "$BASE/api/v1/payroll/cycles/" \
  -d "{\n    \"name\": \"Cycle $(date +%Y-%m)\",\n    \"description\": \"Monthly payroll run\",\n    \"frequency\": \"monthly\",\n    \"period_start\": \"$START\",\n    \"period_end\": \"$END\",\n    \"cutoff_date\": \"$END\",\n    \"eligibility_criteria\": \"list\",\n    \"eligible_employees\": [$EMP_ID]\n  }")
CYCLE_ID=$(echo "$CYCLE" | jq -r .id)
echo "Cycle created: id=$CYCLE_ID"

# ---------- 7) Run Payroll ----------
header "7) Run payroll for the cycle"
req POST "$BASE/api/v1/payroll/records/run_cycle/" -d "{\"cycle\":\"$CYCLE_ID\"}" | jq .

# ---------- 8) Inspect Records & Reports ----------
header "8) Payroll records (by employee)"
req GET "$BASE/api/v1/payroll/records/?employee=$EMP_ID" | jq .

header "Payroll report (range)"
req GET "$BASE/api/v1/payroll/reports?start=$START&end=$END" | jq .

# ---------- 9) Bank Details & Dependents ----------
header "9) Add Bank Details (nested under employee)"
BANK=$(req POST "$BASE/api/v1/employees/$EMP_ID/bank-details/" \
  -d '{"bank_name":"ACME Bank","branch":"Main","swift_bic":"ACMEUS00","account_name":"Main Payroll","account_number":"1234567890","iban":"ACME1234567890"}')
echo "$BANK" | jq .

header "Add a Dependent (nested)"
DEP=$(req POST "$BASE/api/v1/employees/$EMP_ID/dependents/" \
  -d '{"name":"Sam Example","relationship":"Child","date_of_birth":"2015-06-15"}')
echo "$DEP" | jq .

# ---------- Done ----------
header "Done"
echo "All steps completed. You can now explore the created data via /api/v1/… endpoints."

# ---------------------- Optional: cookie-based auth ----------------------
: <<'COOKIE_FLOW'
# If you prefer HttpOnly cookie-based sessions instead of Bearer tokens:
# 1) Login (stores cookies in cookies.txt)
curl -sS -X POST "$BASE/api/v1/auth/login/" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\"}" \
  -c cookies.txt | jq .

# 2) Subsequent requests must send cookies (-b cookies.txt) and do NOT use Authorization header
curl -sS "$BASE/api/v1/users/me/" -b cookies.txt | jq .

# 3) Refresh to rotate tokens in cookies
curl -sS -X POST "$BASE/api/v1/auth/jwt/refresh/" -b cookies.txt | jq .

# 4) Logout clears cookies
curl -sS -X POST "$BASE/api/v1/auth/logout/" -b cookies.txt | jq .
COOKIE_FLOW
