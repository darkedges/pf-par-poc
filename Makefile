.DEFAULT_GOAL := help
# Keep lifecycle operations sequential, including when invoked with make -j.
.NOTPARALLEL:

PWSH ?= pwsh
PYTHON ?= python
REFERENCE_PROJECT ?= ../pingfederate-graph-broker
DOCKER_HOST ?= npipe:////./pipe/dockerDesktopLinuxEngine

MANAGE = "$(PWSH)" -NoProfile -NonInteractive -File scripts/manage.ps1 -Python "$(PYTHON)" -DockerHost "$(DOCKER_HOST)"

.PHONY: help doctor prepare deps init bootstrap deploy up plan fmt fmt-check validate test test-live check status logs start stop destroy

help doctor deps init bootstrap deploy plan fmt fmt-check validate test test-live status logs start stop destroy:
	$(MANAGE) -Action $@

prepare:
	$(MANAGE) -Action prepare -ReferenceProject "$(REFERENCE_PROJECT)"

up: deploy

check: fmt-check validate test
