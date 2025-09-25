@echo off
setlocal enabledelayedexpansion

REM Pull images from Docker Hub and retag to local compose names
REM Usage:
REM   scripts\win\pull-retag.cmd <DOCKERHUB_NAMESPACE> [TAG]

if "%~1"=="" (
  echo Missing DOCKERHUB_NAMESPACE ^(your Docker Hub username or org^)
  echo Usage: %~nx0 DOCKERHUB_NAMESPACE [TAG]
  exit /b 1
)

set NAMESPACE=%~1
set TAG=%~2
if "%TAG%"=="" set TAG=latest

set REPO_PREFIX=hr-payroll
set SERVICES=django postgres traefik nginx celeryworker celerybeat flower

for %%S in (%SERVICES%) do (
  set "REMOTE=%NAMESPACE%/%REPO_PREFIX%-%%S:%TAG%"
  set "LOCAL=hr_payroll_production_%%S"
  echo Pulling !REMOTE!
  docker pull !REMOTE! || exit /b 1
  echo Retagging !REMOTE! as !LOCAL!
  docker tag !REMOTE! !LOCAL! || exit /b 1
)

echo Done. You can now run: docker compose -f docker-compose.production.yml up -d
endlocal
