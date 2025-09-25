Audit Logging
======================================================================

Overview
----------------------------------------------------------------------

An AuditLog model captures key events, such as user login and profile updates.
Signals and view hooks are used to write to the audit log.

Implemented Events
----------------------------------------------------------------------

- User login (via django-allauth signal)
- User profile update (UserViewSet.perform_update)

Extending
----------------------------------------------------------------------

Add additional events by invoking the audit utility from views or signals.

