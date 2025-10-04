# hr_payroll

this is a robust and centralized project that automates manual hr and payroll systems with a wb based system

[![Built with Cookiecutter Django](https://img.shields.io/badge/built%20with-Cookiecutter%20Django-ff69b4.svg?logo=cookiecutter)](https://github.com/cookiecutter/cookiecutter-django/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

License: MIT

## Settings

Moved to [settings](https://cookiecutter-django.readthedocs.io/en/latest/1-getting-started/settings.html).

## API overview

- Base prefixes: the project exposes both unversioned and versioned API routes.
  - Unversioned: `/api/` (namespace: `api`)
  - Versioned: `/api/v1/` (namespace: `api_v1`) — current alias of `/api/`
- OpenAPI schema and docs:
  - JSON schema: `/api/schema/` and `/api/v1/schema/`
  - Swagger UI: `/api/docs/` and `/api/v1/docs/`
- Authentication:
  - Token/JWT: `dj-rest-auth` under `/api/auth/…` and `/api/v1/auth/…`
  - User management: `djoser` routes are mounted under the same `/api/auth/…` prefix.

### Employees module (Iteration 1)

Models:

- Department: simple department catalog.
- Employee: one-to-one with `users.User`, optional `department`, `title`, `hire_date`.
- EmployeeDocument: file uploads associated with an employee.

Endpoints (DRF viewsets):

- Departments: `GET/POST /api/v1/departments/`, `GET/PATCH/PUT/DELETE /api/v1/departments/{id}/`
- Employees: `GET/POST /api/v1/employees/`, `GET/PATCH/PUT/DELETE /api/v1/employees/{id}/`
- Employee Documents: `GET/POST /api/v1/employee-documents/`, `GET /api/v1/employee-documents/{id}/`

Permissions (summary):

- Admins and Managers can create/update/delete employees and departments.
- Regular employees can list and retrieve, and only see their own `Employee` record and their own `EmployeeDocument` items.

Note: File uploads require MEDIA settings to be configured in your environment; in development, use the default MEDIA_ROOT served by Django or your chosen storage.

### Seed default RBAC groups

Seed three default groups and sensible base permissions for the `User` model:

    python manage.py setup_rbac

This creates groups: `Admin`, `Manager`, and `Employee`.

- Admin: full permissions on users
- Manager: view/change users
- Employee: view users

You can assign users to these groups via the Django admin or programmatically.

## Basic Commands

### Setting Up Your Users

- To create a **normal user account**, just go to Sign Up and fill out the form. Once you submit it, you'll see a "Verify Your E-mail Address" page. Go to your console to see a simulated email verification message. Copy the link into your browser. Now the user's email should be verified and ready to go.

- To create a **superuser account**, use this command:

      python manage.py createsuperuser

For convenience, you can keep your normal user logged in on Chrome and your superuser logged in on Firefox (or similar), so that you can see how the site behaves for both kinds of users.

### Type checks

Running type checks with mypy:

    mypy hr_payroll

### Test coverage

To run the tests, check your test coverage, and generate an HTML coverage report:

    coverage run -m pytest
    coverage html
    open htmlcov/index.html

#### Running tests with pytest

    pytest

### Live reloading and Sass CSS compilation

Moved to [Live reloading and SASS compilation](https://cookiecutter-django.readthedocs.io/en/latest/2-local-development/developing-locally.html#using-webpack-or-gulp).

### Celery

This app comes with Celery.

To run a celery worker:

    cd hr_payroll
    celery -A config.celery_app worker -l info

Please note: For Celery's import magic to work, it is important _where_ the celery commands are run. If you are in the same folder with _manage.py_, you should be right.

To run [periodic tasks](https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html), you'll need to start the celery beat scheduler service. You can start it as a standalone process:

    cd hr_payroll
    celery -A config.celery_app beat

or you can embed the beat service inside a worker with the `-B` option (not recommended for production use):

    cd hr_payroll
    celery -A config.celery_app worker -B -l info

### Email Server

In development, it is often nice to be able to see emails that are being sent from your application. For that reason local SMTP server [Mailpit](https://github.com/axllent/mailpit) with a web interface is available as docker container.

Container mailpit will start automatically when you will run all docker containers.
Please check [cookiecutter-django Docker documentation](https://cookiecutter-django.readthedocs.io/en/latest/2-local-development/developing-locally-docker.html) for more details how to start all containers.

With Mailpit running, to view messages that are sent by your application, open your browser and go to `http://127.0.0.1:8025`

### Sentry

Sentry is an error logging aggregator service. You can sign up for a free account at <https://sentry.io/signup/?code=cookiecutter> or download and host it yourself.
The system is set up with reasonable defaults, including 404 logging and integration with the WSGI application.

You must set the DSN url in production.

## Deployment

The following details how to deploy this application.

### Docker

See detailed [cookiecutter-django Docker documentation](https://cookiecutter-django.readthedocs.io/en/latest/3-deployment/deployment-with-docker.html).

### Custom Bootstrap Compilation

The generated CSS is set up with automatic Bootstrap recompilation with variables of your choice.
Bootstrap v5 is installed using npm and customised by tweaking your variables in `static/sass/custom_bootstrap_vars`.

You can find a list of available variables [in the bootstrap source](https://github.com/twbs/bootstrap/blob/v5.1.3/scss/_variables.scss), or get explanations on them in the [Bootstrap docs](https://getbootstrap.com/docs/5.1/customize/sass/).

Bootstrap's javascript as well as its dependencies are concatenated into a single file: `static/js/vendors.js`.

## Onboarding Username & Email Generation

When creating a new employee via the endpoint `POST /api/v1/employees/onboard/new/`, if `username` and/or `email` are omitted they are auto-generated using a deterministic compact pattern:

    <first-initial><truncated-last><sequence>

Example: `John Robertson` -> `jrobert001` (email: `jrobert001@hr_payroll.com`). The sequence is zero-padded to ensure stable sorting and starts at `001` for each distinct name root.

### Environment Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `ONBOARDING_EMAIL_DOMAIN` | `hr_payroll.com` | Domain appended to generated username for the email address. |
| `ONBOARDING_LAST_NAME_LENGTH` | `6` | Maximum characters from the slugified last name to retain. |
| `ONBOARDING_SEQUENCE_PAD` | `3` | Zero-padding width for the numeric sequence (e.g. 001, 002). |

The generator is collision-safe (will increment the sequence until a unique username & email are found) and accent/whitespace tolerant (names are slugified).

If both first and last name are missing, it falls back to pattern: `uuser001`, `uuser002`, etc.

These values can be tuned without code changes by setting the corresponding environment variables.
