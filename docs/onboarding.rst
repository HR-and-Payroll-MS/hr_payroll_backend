Onboarding Flow
======================================================================

Overview
----------------------------------------------------------------------
The onboarding system provides two manager/admin-only endpoints to create or
promote employees while automatically generating credentials.

Endpoints
----------------------------------------------------------------------
- Create new User + Employee: ``POST /api/v1/employees/onboard/new``
- Promote existing User to Employee: ``POST /api/v1/employees/onboard/existing``

Username & Email Generation
----------------------------------------------------------------------
Pattern (deterministic, collision-resistant):

.. code-block:: text

    <first-initial><truncated-last><sequence>

Rules:
- ``first-initial``: first letter of provided first name (lowercased; fallback ``u``)
- ``truncated-last``: slugified last name (fallback ``user``) limited by
  ``ONBOARDING_LAST_NAME_LENGTH`` (default 6)
- ``sequence``: zero-padded integer starting at ``001`` with width
  ``ONBOARDING_SEQUENCE_PAD`` (default 3) used only when earlier candidate exists

Example:
- First: John, Last: Robertson  -> ``jrobert001``
- Collision for another John Robertson -> ``jrobert002``

The email local-part equals the generated username and the domain is taken from
``ONBOARDING_EMAIL_DOMAIN`` (default ``hr_payroll.com``):

.. code-block:: text

    jrobert001@hr_payroll.com

Password Generation
----------------------------------------------------------------------
A secure random password (default length 12) is generated with at least one:
- Lowercase letter
- Uppercase letter
- Digit
- Symbol from the curated set ``!@#$%^&*+-_``

The password is never accepted from client input and is only returned once in
the onboarding response (and temporarily via the credential recovery endpoints).

Response Shape (New User Onboarding)
----------------------------------------------------------------------
Excerpt of response (fields unrelated to credentials elided):

.. code-block:: json

    {
      "id": 17,
      "user": {
        "id": 42,
        "username": "jrobert001",
        "email": "jrobert001@hr_payroll.com",
        "first_name": "John",
        "last_name": "Robertson",
        "is_active": true
      },
      "department": {"id": 3, "name": "Engineering", "description": ""},
      "title": "Engineer",
      "credentials": {
        "username": "jrobert001",
        "email": "jrobert001@hr_payroll.com",
        "initial_password": "Ab9!xYt2Qw$z"
      }
    }

Notes:
- The ``credentials`` block is omitted if generation was not needed (e.g., existing user onboarding).

Existing User Promotion
----------------------------------------------------------------------
Body example:

.. code-block:: json

    { "user": "alice", "department": 3, "title": "Analyst" }

Validation:
- User must not already have an Employee.
- Department optional (nullable) and title optional.

Security
----------------------------------------------------------------------
- Only Admin or Manager can call onboarding endpoints.
- Email is marked verified and primary (django-allauth) on creation.

Refer to :doc:`settings` for configuration of generation parameters.
