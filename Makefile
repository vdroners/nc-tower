APP_ID ?= nc_tower
ROOT := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
CONTAINER ?= cloud_app
REMOTE := /var/www/html/custom_apps/$(APP_ID)
# Estate default: lab mounts. Generic App Store compose: make sidecar-up-generic
SIDECAR_COMPOSE := docker compose -f "$(ROOT)sidecar/docker-compose.lab.yml"
SIDECAR_COMPOSE_GENERIC := docker compose -f "$(ROOT)sidecar/docker-compose.yml"

.PHONY: build deploy ship gate-preflight sidecar-up sidecar-up-generic sidecar-down bump-patch bump-minor test lint appstore appstore-sign

# 1.9: the four prebuilt Admin Cockpit bundles are gone; js/ is built from src/.
build:
	cd "$(ROOT)" && (npm ci --no-audit --no-fund || npm install --no-audit --no-fund)
	cd "$(ROOT)" && npm run build
	@test -f "$(ROOT)js/nc_tower-app.js" || (echo "build did not emit js/nc_tower-app.js" && exit 1)
	@test -f "$(ROOT)js/nc_tower-widget.js" || (echo "build did not emit js/nc_tower-widget.js" && exit 1)

test:
	cd "$(ROOT)" && npm run test

lint:
	cd "$(ROOT)" && npm run lint

deploy: build
	@test -n "$$(docker ps -q -f name=$(CONTAINER))" || (echo "Container $(CONTAINER) not running" && exit 1)
	docker exec $(CONTAINER) mkdir -p $(REMOTE)
	for dir in appinfo img js lib templates l10n screenshots docs tools sidecar; do \
		if [ -d "$(ROOT)$$dir" ]; then \
			docker exec $(CONTAINER) rm -rf $(REMOTE)/$$dir; \
			docker cp "$(ROOT)$$dir/." $(CONTAINER):$(REMOTE)/$$dir/; \
		fi; \
	done
	for f in LICENSE README.md CREDITS.md CHANGELOG.md CODE_OF_CONDUCT.md; do \
		if [ -f "$(ROOT)$$f" ]; then docker cp "$(ROOT)$$f" $(CONTAINER):$(REMOTE)/; fi; \
	done
	@# The sidecar token is host-root equivalent and PHP reads it from config.php,
	@# never from this file. Keep it out of the web-app tree entirely.
	docker exec $(CONTAINER) rm -rf $(REMOTE)/sidecar/.env $(REMOTE)/sidecar/__pycache__
	@docker exec $(CONTAINER) chown -R www-data:www-data $(REMOTE) 2>/dev/null || true
	docker exec -u www-data $(CONTAINER) php /var/www/html/occ app:enable $(APP_ID) || true
	docker exec -u www-data $(CONTAINER) php /var/www/html/occ upgrade || true
	@docker exec -u www-data $(CONTAINER) php -r 'function_exists("opcache_reset") && @opcache_reset();' 2>/dev/null || true
	@if [ "$(RESTART)" = "1" ]; then \
		echo "RESTART=1 -> restarting $(CONTAINER)"; \
		docker restart $(CONTAINER) >/dev/null && sleep 8; \
	fi
	@echo "Deployed $(APP_ID) to $(CONTAINER):$(REMOTE)"

sidecar-up:
	$(SIDECAR_COMPOSE) up -d
	@echo "sidecar (lab) on 127.0.0.1:18765"

sidecar-up-generic:
	$(SIDECAR_COMPOSE_GENERIC) up -d --build
	@echo "sidecar (generic) on 127.0.0.1:18765"

sidecar-down:
	-$(SIDECAR_COMPOSE) down
	-$(SIDECAR_COMPOSE_GENERIC) down

ship: build sidecar-up deploy gate-preflight
	@echo "ship complete"

gate-preflight:
	bash "$(ROOT)tools/tower-preflight.sh"
	@test -n "$$(docker ps -q -f name=$(CONTAINER))" || (echo "cloud_app not running" && exit 1)
	docker exec $(CONTAINER) php $(REMOTE)/tools/tower-api-gates.php
	@# G25 needs a real Nextcloud bootstrap to ask the router what a URL resolves to.
	docker exec -u www-data $(CONTAINER) php $(REMOTE)/tools/tower-route-gates.php

DATE ?= $(shell date +%F)
bump-patch:
	@$(MAKE) --no-print-directory _bump PART=patch
bump-minor:
	@$(MAKE) --no-print-directory _bump PART=minor

_bump:
	@cur=$$(grep -oE '<version>[0-9]+\.[0-9]+\.[0-9]+</version>' "$(ROOT)appinfo/info.xml" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+'); \
	test -n "$$cur" || (echo "could not read version" && exit 1); \
	maj=$$(echo $$cur | cut -d. -f1); min=$$(echo $$cur | cut -d. -f2); pat=$$(echo $$cur | cut -d. -f3); \
	if [ "$(PART)" = "minor" ]; then min=$$((min+1)); pat=0; else pat=$$((pat+1)); fi; \
	next="$$maj.$$min.$$pat"; \
	sed -i "s#<version>$$cur</version>#<version>$$next</version>#" "$(ROOT)appinfo/info.xml"; \
	sed -i "s#\"version\": \"$$cur\"#\"version\": \"$$next\"#" "$(ROOT)package.json"; \
	sed -i "s#\*\*Version $$cur\*\*#**Version $$next**#" "$(ROOT)README.md"; \
	if ! grep -q "^## \[$$next\]" "$(ROOT)CHANGELOG.md"; then \
		awk -v v="$$next" -v d="$(DATE)" 'BEGIN{done=0} /^## \[/ && !done {print "## [" v "] - " d "\n"; done=1} {print}' \
			"$(ROOT)CHANGELOG.md" > "$(ROOT)CHANGELOG.md.tmp" && mv "$(ROOT)CHANGELOG.md.tmp" "$(ROOT)CHANGELOG.md"; \
	fi; \
	echo "Bumped $$cur -> $$next"

VERSION := $(shell grep -oE '<version>[0-9]+\.[0-9]+\.[0-9]+</version>' "$(ROOT)appinfo/info.xml" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')
STAGING := /tmp/$(APP_ID)-$(VERSION)
TARBALL := /tmp/$(APP_ID)-$(VERSION).tar.gz

# Self-contained App Store tarball (built assets; sidecar source included, .env excluded).
appstore: build
	rm -rf "$(STAGING)"
	mkdir -p "$(STAGING)"
	rsync -a --delete \
		--exclude node_modules --exclude .git --exclude .github \
		--exclude src --exclude tests --exclude .cursor --exclude '*.map' \
		--exclude sidecar/.env --exclude sidecar/__pycache__ \
		--exclude .vitest-gate-stamp --exclude scripts --exclude tools \
		--exclude webpack.config.js --exclude vitest.config.cjs \
		"$(ROOT)" "$(STAGING)/"
	rm -rf "$(STAGING)/node_modules"
	tar -czf "$(TARBALL)" -C /tmp "$(APP_ID)-$(VERSION)"
	@echo "Release tarball: $(TARBALL)"

appstore-sign: appstore
	@test -n "$(NC_OCC)" || (echo "Set NC_OCC to your occ binary path" && exit 1)
	@test -n "$$APP_PRIVATE_KEY" || (echo "Set APP_PRIVATE_KEY to private key file path" && exit 1)
	@test -n "$$APP_PUBLIC_CRT" || (echo "Set APP_PUBLIC_CRT to certificate file path" && exit 1)
	cp "$(ROOT)scripts/file_from_env.php" "$(STAGING)/file_from_env.php"
	php "$(NC_OCC)" integrity:sign-app \
		--privateKey="file://$(STAGING)/file_from_env.php" \
		--certificate="file://$(STAGING)/file_from_env.php" \
		$(APP_ID)
	APP_PRIVATE_KEY="$$APP_PRIVATE_KEY" APP_PUBLIC_CRT="$$APP_PUBLIC_CRT" \
	php "$(NC_OCC)" integrity:check-app $(APP_ID)
	tar -czf "$(TARBALL)" -C /tmp "$(APP_ID)-$(VERSION)"
	@echo "Signed tarball: $(TARBALL)"
