@echo off
setlocal enabledelayedexpansion

REM Build, tag, and push all production images to Docker Hub (Windows cmd)
REM Usage:
REM   scripts\win\release-dockerhub.cmd <DOCKERHUB_NAMESPACE> [TAG]
REM Example:
REM   scripts\win\release-dockerhub.cmd yourname v1.0.0

if "%~1"=="" (
  echo Missing DOCKERHUB_NAMESPACE ^(your Docker Hub username or org^)
  echo Usage: %~nx0 DOCKERHUB_NAMESPACE [TAG]
  exit /b 1
)

set NAMESPACE=%~1
set TAG=%~2
if "%TAG%"=="" set TAG=latest

set REPO_PREFIX=hr-payroll
set COMPOSE_FILE=docker-compose.production.yml

echo Logging in to Docker Hub (skip if already logged in)...
docker login || (
  echo Docker login failed. Please login and re-run.
  exit /b 1
)

echo Building images defined in %COMPOSE_FILE% ...
docker compose -f %COMPOSE_FILE% build --pull || (
  echo Build failed.
  exit /b 1
)

set SERVICES=django postgres traefik nginx celeryworker celerybeat flower

for %%S in (%SERVICES%) do (
  set "LOCAL=hr_payroll_production_%%S"
  set "REMOTE=%NAMESPACE%/%REPO_PREFIX%-%%S:%TAG%"

  echo Tagging !LOCAL! as !REMOTE!
  docker image inspect !LOCAL! >NUL 2>&1 || (
    echo Local image !LOCAL! not found. Did the build succeed?
    exit /b 1
  )
  docker tag !LOCAL! !REMOTE! || exit /b 1
  echo Pushing !REMOTE!
  docker push !REMOTE! || exit /b 1
)

echo Done. Pushed tags under %NAMESPACE% with tag %TAG%.
endlocal
