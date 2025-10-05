 .. _users:

Users
======================================================================

Starting a new project, it’s highly recommended to set up a custom user model,
even if the default User model is sufficient for you.

This model behaves identically to the default user model,
but you’ll be able to customize it in the future if the need arises.

.. automodule:: hr_payroll.users.models
   :members:
   :noindex:

Field Immutability & Onboarding Generation
------------------------------------------

User ``username`` and ``email`` values are not arbitrarily editable via the
public API. They are generated deterministically during the onboarding process
from an employee's first name, last name (truncated), and a zero‑padded
sequence counter. This guarantees uniqueness, auditability, and prevents drift
between identity attributes and HR records.

Update Rules:

* ``first_name`` and ``last_name``: May be updated by the user (or elevated roles).
* ``username`` (read-only): Auto-generated; attempts to send this field in PATCH/PUT
   will return ``400`` with a validation error.
* ``email`` (read-only): Auto-generated to match the derived username plus the
   configured domain (``ONBOARDING_EMAIL_DOMAIN``); PATCH/PUT attempts are rejected
   with ``400``.
* Group membership: Managed internally (displayed read-only).

Rationale:

Locking these fields avoids inconsistencies when external systems (payroll,
access control, SSO) rely on a stable naming convention. If a correction is
required (e.g. legal name change), the onboarding regeneration / administrative
process should be followed rather than directly mutating username/email.

Error Response Example (attempting to change username/email)::

   {
      "username": ["This field is read-only and auto-generated. Use onboarding to change it."],
      "email": ["This field is read-only and auto-generated. Use onboarding to change it."]
   }

See also: :ref:`onboarding` and :ref:`settings` for configuration values
controlling truncation length and sequence padding.
