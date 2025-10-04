Settings Reference
======================================================================

This page documents custom settings that influence onboarding and credential
recovery behavior.

Onboarding & Credential Generation
----------------------------------------------------------------------
``ONBOARDING_EMAIL_DOMAIN``
  Domain appended to generated usernames for email creation.
  Default: ``hr_payroll.com``

``ONBOARDING_LAST_NAME_LENGTH``
  Maximum number of characters (after slugification) from the last name used
  in the generated username.
  Default: ``6``

``ONBOARDING_SEQUENCE_PAD``
  Zero-pad width for the numeric sequence ensuring uniqueness.
  Default: ``3`` (e.g., ``001``)

``ONBOARDING_CREDENTIAL_TTL_MINUTES``
  Minutes credentials remain retrievable via the *initial credentials* endpoint
  before returning 404. Regeneration will create a fresh cache entry.
  Default: ``30``

Password Generation
----------------------------------------------------------------------
The password generator uses a curated symbol set ``!@#$%^&*+-_`` and enforces
inclusion of at least one lowercase, uppercase, digit, and symbol.

Environment & Overriding
----------------------------------------------------------------------
All settings can be overridden in environment-specific settings modules, e.g.
``config/settings/local.py`` or via environment variables (if the project uses
``django-environ`` or similar) by assigning these names.

Versioning Policy
----------------------------------------------------------------------
Settings affecting username/email patterns should be changed cautiously in
production; altering them midstream can create divergent patterns across user
cohorts. Prefer increasing the sequence space (``ONBOARDING_SEQUENCE_PAD``) if
collisions become likely.
