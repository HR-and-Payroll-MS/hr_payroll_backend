# HR Payroll API Reference (Human-Friendly)

Version: 1.0.0
Base URL (production): `https://hr-payroll.com`

This document gives frontend developers a concise, readable mapping of every public REST endpoint. It summarizes: purpose, auth method, required fields, expected responses, role restrictions, and notes.

---
## 1. Authentication & Security Overview

The API supports three auth mechanisms (depending on endpoint group):

| Mechanism | How to use | Typical Header / Cookie | When Used |
|-----------|------------|--------------------------|-----------|
| JWT (Bearer) | Obtain via `/api/v1/auth/jwt/create/` then add header | `Authorization: Bearer <access>` | Most protected endpoints |
| Session (Cookie) | Login via `/api/v1/auth/login/` (session cookie) | `__Secure-sessionid` cookie | Browsers / dj-rest-auth flows |
| Token (DRF Token) | (If issued) add header | `Authorization: Token <key>` | Legacy / optional support |

Priority of use (recommended): **JWT**.
Some endpoints list multiple schemes—any one valid scheme works.

### Role Model (Business Logic)

Certain employee onboarding & credential endpoints are restricted to **Manager** or **Admin** roles (enforced server-side). If a role is not mentioned, any authenticated user can use the endpoint (subject to standard object-level permissions).

---
## 2. Status Code Conventions

| Code | Meaning |
|------|---------|
| 200  | Success (GET/PUT/PATCH/POST actions returning a body) |
| 201  | Resource created |
| 204  | Success, no body (DELETE) |
| 400  | Validation / input error |
| 401  | Not authenticated or invalid token |
| 403  | Authenticated but not permitted (role or ownership) |
| 404  | Not found (or expired credential cache) |

---
## 3. Schema & Tag Groups

Tags (logical groupings):
- **JWT Authentication** – issue/refresh/verify tokens
- **Session Auth** – session login/logout/password flows
- **Authentication** – current user profile (dj-rest-auth consolidated view)
- **User Management** – Djoser user CRUD, activation, resets (Manager/Admin sensitive operations restricted)
- **Users** – Public/basic user listing & detail (read-only representations)
- **Employees** – Employee listing, onboarding, credential regeneration (Manager/Admin)
- **Employee Documents** – Upload/manage documents tied to employees
- **Departments** – Department CRUD

---
## 4. Field / Data Model Highlights

### User (Read models)
```jsonc
{
  "username": "jrobert001",
  "first_name": "John",
  "last_name": "Robertson",
  "full_name": "John Robertson",      // derived
  "email": "jrobert001@hr_payroll.com",
  "groups": ["Managers"],              // role indicators via groups
  "url": "https://hr-payroll.com/api/v1/users/jrobert001/"
}
```
`username` and `email` are **immutable** once set (update attempts will error).

### Employee
```jsonc
{
  "id": 12,
  "user": "jrobert001",  // write-only when creating (or a username field depending on serializer)
  "department": 3,         // optional, nullable
  "title": "HR Manager",
  "hire_date": "2025-10-01"
}
```
Certain create flows instead return a **nested** user object (onboarding responses may include generated credentials block). Credentials only appear immediately at creation or regeneration and are cached for a short TTL.

### Employee Document
```jsonc
{
  "id": 44,
  "employee": 12,
  "name": "Passport Scan",
  "file": "https://cdn.hr-payroll.com/media/docs/passport.pdf",
  "uploaded_at": "2025-10-07T12:33:11Z"
}
```

---
## 5. Endpoint Details

### 5.1 JWT Authentication

#### POST `/api/v1/auth/jwt/create/`
Issue access + refresh tokens.
- **Auth Required**: No (you provide credentials)
- **Request**
```json
{ "username": "alice", "password": "Secret123!" }
```
- **Success (200)**
```json
{ "refresh": "<jwt-refresh>", "access": "<jwt-access>" }
```
- **Errors**: 401 invalid credentials.

#### POST `/api/v1/auth/jwt/refresh/`
Refresh an access token.
- **Request**
```json
{ "refresh": "<jwt-refresh>" }
```
- **Success (200)**
```json
{ "access": "<new-access>", "refresh": "<original-refresh-or-rotated>" }
```

#### POST `/api/v1/auth/jwt/verify/`
Verify structure & signature of a token.
- **Request**
```json
{ "token": "<any-jwt>" }
```
- **Success (200)**: Echo structure (schema-only); invalid returns 401/400.

### 5.2 Session Auth (dj-rest-auth)

#### POST `/api/v1/auth/login/`
Create session + optional token.
- **Request** (any one of username/email + password accepted if backend configured):
```json
{ "username": "alice", "password": "Secret123!" }
```
- **Success (200)**
```json
{ "key": "<drf-token-if-enabled>" }
```

#### POST `/api/v1/auth/logout/`
Invalidate session (and DRF token if present). No body required.
- **Success (200)** `{ "detail": "Successfully logged out." }`

#### POST `/api/v1/auth/password/change/`
Change current user password (must be authenticated).
- **Request**
```json
{ "new_password1": "NewPass#1", "new_password2": "NewPass#1" }
```
- **Success (200)** detail message.

#### POST `/api/v1/auth/password/reset/`
Initiate email reset link.
```json
{ "email": "user@example.com" }
```

#### POST `/api/v1/auth/password/reset/confirm/`
Complete password reset.
```json
{ "uid": "<uidb64>", "token": "<token>", "new_password1": "New#Pass1", "new_password2": "New#Pass1" }
```

### 5.3 Current Authenticated User Profile

Endpoint: `/api/v1/auth/user/` (GET / PUT / PATCH)
- **Auth**: Required (JWT / session / token)
- **Immutable fields**: `email`, `username`
- **Update (PUT/PATCH) Request Example**
```json
{ "first_name": "Alice", "last_name": "Smith" }
```
- **Response (200)** returns updated profile.

### 5.4 User Management (Administrative / Self-Service via Djoser)

Base collection: `/api/v1/auth/users/`

| Method & Path | Purpose | Notes |
|---------------|---------|-------|
| GET `/api/v1/auth/users/` | List users | Restricted to elevated roles (Manager/Admin) depending on permission class. |
| POST `/api/v1/auth/users/` | Create user | Provides `username`, `email`, `password`, `re_password`. |
| GET `/api/v1/auth/users/{id}/` | Retrieve user | |
| PUT/PATCH `/api/v1/auth/users/{id}/` | Update (limited) | Username/email may be enforced read-only by custom logic. |
| DELETE `/api/v1/auth/users/{id}/` | Delete user | 204 on success. |

Other related endpoints:
- POST `/api/v1/auth/users/activation/` – Activate account (Manager/Admin only).
- POST `/api/v1/auth/users/resend_activation/`
- POST `/api/v1/auth/users/reset_password/`
- POST `/api/v1/auth/users/reset_password_confirm/`
- POST `/api/v1/auth/users/reset_username/` (Manager/Admin only)
- POST `/api/v1/auth/users/reset_username_confirm/`
- POST `/api/v1/auth/users/set_password/` – Authenticated user changes password with current password verification.
- POST `/api/v1/auth/users/set_username/` – (If allowed; may be blocked by immutability rule.)
- `.../users/me/` (GET/PUT/PATCH/DELETE) – Self-focused variant.

### 5.5 Public / Read-Oriented Users API

`/api/v1/users/` & `/api/v1/users/{username}/`
- GET list: array of user objects (read-only fields) – may be restricted to authenticated.
- GET detail: single user.
- PUT/PATCH/DELETE on detail path exist in schema but **username/email immutability** enforced; frontend should *not* attempt to modify those fields.

### 5.6 Employees

#### GET `/api/v1/employees/`
List employees.
#### GET `/api/v1/employees/{id}/`
Retrieve one.
#### PUT/PATCH `/api/v1/employees/{id}/`
Update `department`, `title`, `hire_date`.
#### DELETE `/api/v1/employees/{id}/`
Remove employee record (does not necessarily delete underlying user unless backend logic ties them).

#### Onboarding Endpoints (Manager/Admin)

1. **POST** `/api/v1/employees/onboard/new/`
   Create new User + Employee with auto-generated `username`, `email`, secure password.
   - **Request** (supply names & optional metadata):
   ```json
   { "first_name": "John", "last_name": "Robertson", "department": 3, "title": "HR Analyst" }
   ```
   - **Success (201)** Example (simplified):
   ```json
   {
     "employee": { "id": 55, "department": 3, "title": "HR Analyst", "hire_date": null },
     "user": { "username": "jrober001", "email": "jrober001@hr_payroll.com", "first_name": "John", "last_name": "Robertson" },
     "credentials": { "username": "jrober001", "email": "jrober001@hr_payroll.com", "password": "Q4$k..." }
   }
   ```
   Credentials block only appears once (and briefly retrievable via initial-credentials endpoint while cached).

2. **POST** `/api/v1/employees/onboard/existing/`
   Promote an existing user to Employee.
   - **Request**
   ```json
   { "user": "existinguser", "department": 3, "title": "Dev" }
   ```
   - **Response (201)** Employee object.

#### Credential Cache Endpoints (Manager/Admin)

- **GET** `/api/v1/employees/{id}/initial-credentials/`
  - Returns the original generated credentials if TTL not expired.
  - **200** Example:
  ```json
  { "username": "jrober001", "email": "jrober001@hr_payroll.com", "password": "Q4$k..." }
  ```
  - **404** if expired.

- **POST** `/api/v1/employees/{id}/regenerate-credentials/`
  - Generates a NEW secure password, invalidates previous, caches again.
  - **200** returns new credentials block (same shape as above).

### 5.7 Employee Documents

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/employee-documents/` | List documents (may filter client-side) |
| POST | `/api/v1/employee-documents/` | Upload new (multipart or JSON with file ref) |
| GET | `/api/v1/employee-documents/{id}/` | Retrieve one |
| PUT/PATCH | `/api/v1/employee-documents/{id}/` | Update name / file |
| DELETE | `/api/v1/employee-documents/{id}/` | Remove (204) |

**Create Request Example** (multipart form):
```
name=Passport Scan
employee=12
file=<binary>
```
**Success (201)** returns full object.

### 5.8 Departments

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/departments/` | List all departments |
| POST | `/api/v1/departments/` | Create new department |
| GET | `/api/v1/departments/{id}/` | Retrieve one |
| PUT/PATCH | `/api/v1/departments/{id}/` | Update name/description |
| DELETE | `/api/v1/departments/{id}/` | Remove (204) |

**Create Example**
```json
{ "name": "Finance", "description": "Handles budgets" }
```

### 5.9 OpenAPI Schema Endpoint

GET `/api/v1/schema/?format=json|yaml` – machine-readable specification (what this file was derived from).

---
## 6. Validation & Errors

Example validation failure (400):
```json
{
  "first_name": ["This field is required."],
  "department": ["Invalid pk '9999' - object does not exist."]
}
```
Immutable field attempt (e.g., changing `username`):
```json
{
  "username": ["Username cannot be modified once set."]
}
```

---
## 7. Frontend Implementation Tips

- Always store **refresh** + **access** tokens if using JWT; refresh before expiry.
- For onboarding: show credentials only once; warn user they expire from cache quickly.
- Treat `employees` onboarding responses as special (nested & credentials). Standard listing endpoints return plain employee objects.
- Use semantic versioning or commit SHA when calling your internal deployment pipeline—unrelated to these endpoints but helpful for tracing API changes.
- Consider ETag / caching for list endpoints later (not currently documented in schema).

---
## 8. Quick Capability Matrix

| Capability | Endpoint(s) | Notes |
|------------|-------------|-------|
| Login (JWT) | `/api/v1/auth/jwt/create/` | Returns access + refresh |
| Refresh token | `/api/v1/auth/jwt/refresh/` | Supply refresh only |
| Verify token | `/api/v1/auth/jwt/verify/` | Structural validity |
| Session login | `/api/v1/auth/login/` | Alternative to JWT |
| Self profile | `/api/v1/auth/user/` | GET/PUT/PATCH |
| List users (admin) | `/api/v1/auth/users/` | Role restricted |
| Onboard new employee | `/api/v1/employees/onboard/new/` | Returns credentials (one-time) |
| Retrieve cached creds | `/api/v1/employees/{id}/initial-credentials/` | TTL-limited |
| Regenerate creds | `/api/v1/employees/{id}/regenerate-credentials/` | Invalidates previous |
| Upload employee document | `/api/v1/employee-documents/` (POST) | Multipart |
| Department CRUD | `/api/v1/departments/` | Standard CRUD |

---
## 9. Change Log (Manual Summary)
- v1.0.0 spec export adapted to human-readable format.
- Username/email immutability enforced in narrative though raw schema may still show them as updatable in some endpoints.

---
## 10. Future Enhancements (Suggested)
- Add explicit role metadata in schema via custom extensions.
- Provide filtering parameters (department, employee name) for list endpoints.
- Add rate limit headers documentation.
- Add pagination examples (if enabled) – not present in current snippets.

---
**End of Document**
