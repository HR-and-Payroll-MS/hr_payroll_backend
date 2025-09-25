# Deploying hr_payroll images to Docker Hub

This guide shows how to build, tag, push, and pull production Docker images for this project using the existing docker-compose.production.yml setup.

Supported shells:

- Windows (cmd.exe)
- Linux/WSL (bash)

Prerequisites

- Docker Desktop installed and running (or Docker Engine on Linux)
- Docker Hub account and credentials
- Cloned repository with this project
- Production env files present: .envs/.production/.django and .envs/.production/.postgres

Images and tags

The compose file builds these images locally:

- hr_payroll_production_django
- hr_payroll_production_postgres
- hr_payroll_production_traefik
- hr_payroll_production_nginx
- hr_payroll_production_celeryworker
- hr_payroll_production_celerybeat
- hr_payroll_production_flower

When pushing to Docker Hub, this guide uses repository names:

- `NAMESPACE`/`hr-payroll-django`:`TAG`
- `NAMESPACE`/`hr-payroll-postgres`:`TAG`
- `NAMESPACE`/`hr-payroll-traefik`:`TAG`
- `NAMESPACE`/`hr-payroll-nginx`:`TAG`
- `NAMESPACE`/`hr-payroll-celeryworker`:`TAG`
- `NAMESPACE`/`hr-payroll-celerybeat`:`TAG`
- `NAMESPACE`/`hr-payroll-flower`:`TAG`

Replace `NAMESPACE` with your Docker Hub username or organization. Choose a `TAG` like `v1.0.0` or `latest`.

Step 1: Login to Docker Hub

- Windows (cmd) [optional command]:

  docker login

- Linux/WSL (bash) [optional command]:

  docker login

Step 2: Build production images locally

- Both platforms [optional command]:

  docker compose -f docker-compose.production.yml build --pull

Step 3: Push images to Docker Hub

- Windows (cmd) [optional command]:

  scripts\win\release-dockerhub.cmd yourname v1.0.0

- Linux/WSL (bash) [optional command]:

  ./scripts/linux/release-dockerhub.sh yourname v1.0.0

This will tag and push all images listed above to Docker Hub under your namespace with the provided tag. Omit the tag to default to latest.

Optional: Pull prebuilt images and run locally

If you want to run the production compose using images from Docker Hub (without rebuilding):

- Windows (cmd) [optional command]:

  scripts\win\pull-retag.cmd yourname v1.0.0

- Linux/WSL (bash) [optional command]:

  ./scripts/linux/pull-retag.sh yourname v1.0.0

Then start services using the standard production compose file:

- Both platforms [optional command]:

  docker compose -f docker-compose.production.yml up -d

Environment and volumes

- Ensure `.envs/.production/.django` and `.envs/.production/.postgres` are filled with correct production settings (secret keys, database URL, allowed hosts, email, etc.).
- `docker-compose.production.yml` defines named volumes for postgres data, redis data, traefik ACME storage, and Django media. These will be created automatically when you run `docker compose up`.

Tagging strategy

- For reproducible deployments, use immutable version tags (e.g., `vYYYY.MM.DD-1`) and also push `latest` if desired.
- Example dual tag push (Linux): you can re-run the push with a second `TAG` to publish the same local images under multiple tags.

Notes

- The traefik service binds 80/443 and expects `traefik.yml` in `compose/production/traefik`; ensure DNS points to your host and that ports are open.
- The django service uses `/start` which will run migrations and collectstatic (as defined in compose scripts). Confirm your settings before first boot.
- The redis service uses the official `redis:6` image pulled from Docker Hub; it is not built locally.

CI/CD (optional)

- You can automate build-and-push in CI. In your workflow, run: `docker login`, `docker build` or `docker compose build`, then tag and push each image with your desired `TAG`. Reuse the command matrix from the scripts for consistency.

Troubleshooting

- If tagging fails: ensure images exist locally (`docker images`) and the build step succeeded.
- If push is denied: verify `docker login` and that you have permission to push to `NAMESPACE`.
- If ACME permissions error in traefik: the volume `production_traefik` must persist and have `600` perms on `acme.json`; the Dockerfile sets this up in the image and volume will persist certificates.
