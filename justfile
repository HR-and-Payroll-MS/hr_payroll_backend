export COMPOSE_FILE := "docker-compose.local.yml"

# Docker image name for production deploys (Render image-backed service)
export DOCKER_IMAGE := "seud/hr-payroll-django"
export DOCKERFILE_PROD := "compose/production/django/Dockerfile"

## Just does not yet manage signals for subprocesses reliably, which can lead to unexpected behavior.
## Exercise caution before expanding its usage in production environments.
## For more information, see https://github.com/casey/just/issues/2473 .


# Default command to list all available commands.
default:
    @just --list

# build: Build python image.
build:
    @echo "Building python image..."
    @docker compose build

# up: Start up containers.
up:
    @echo "Starting up containers..."
    @docker compose up -d --remove-orphans

# down: Stop containers.
down:
    @echo "Stopping containers..."
    @docker compose down

# prune: Remove containers and their volumes.
prune *args:
    @echo "Killing containers and removing volumes..."
    @docker compose down -v {{args}}

# logs: View container logs
logs *args:
    @docker compose logs -f {{args}}

# manage: Executes `manage.py` command.
manage +args:
    @docker compose run --rm django python ./manage.py {{args}}

# migrate: Run Django migrations in container.
migrate:
    @docker compose run --rm django python ./manage.py migrate

# makemigrations: Create new migrations.
makemigrations *apps:
    @docker compose run --rm django python ./manage.py makemigrations {{apps}}

# test: Run pytest in container with warnings enabled.
test:
    @docker compose run --rm django python -Wa -m pytest -q

# prod-build VERSION: Build the production Docker image with a version tag and latest.
prod-build VERSION:
    @echo "Building production image {{DOCKER_IMAGE}}:{{VERSION}}..."
    @docker build -f {{DOCKERFILE_PROD}} -t {{DOCKER_IMAGE}}:{{VERSION}} -t {{DOCKER_IMAGE}}:latest .

# prod-push VERSION: Push the versioned and latest tags to the registry.
prod-push VERSION:
    @echo "Pushing {{DOCKER_IMAGE}}:{{VERSION}} and :latest..."
    @docker push {{DOCKER_IMAGE}}:{{VERSION}}
    @docker push {{DOCKER_IMAGE}}:latest

# render-deploy VERSION [SERVICE_ID]: Trigger a Render deploy for an image-backed service.
# - Provide SERVICE_ID arg, or set env var RENDER_SERVICE_ID beforehand.
render-deploy VERSION SERVICE_ID="${RENDER_SERVICE_ID}":
    @if [ -z "{{SERVICE_ID}}" ]; then \
        echo "ERROR: SERVICE_ID not provided and RENDER_SERVICE_ID not set." >&2; \
        echo "Hint: run 'render services' to find your service id, then export RENDER_SERVICE_ID=..." >&2; \
        exit 1; \
    fi
    @echo "Triggering Render deploy for service {{SERVICE_ID}} using image docker.io/{{DOCKER_IMAGE}}:{{VERSION}}..."
    @render deploys create {{SERVICE_ID}} --image docker.io/{{DOCKER_IMAGE}}:{{VERSION}} --wait

# release VERSION [SERVICE_ID]: Build, push, and deploy to Render.
release VERSION SERVICE_ID="${RENDER_SERVICE_ID}":
    @just prod-build {{VERSION}}
    @just prod-push {{VERSION}}
    @just render-deploy {{VERSION}} {{SERVICE_ID}}
