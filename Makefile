# Convenience targets. Run `make help` for the list.
# dev/uat/production are SEPARATE stacks (own Shopify app, database, backend).
.DEFAULT_GOAL := help
ENV ?= dev
.PHONY: help init dev uat production stop logs db-setup test test-isolated test-ui

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

init: ## Instantiate the template (name the app, create env files)
	node scripts/init-template.mjs

dev: ## Bring up the DEV stack
	./scripts/start-dev.sh

uat: ## Bring up the UAT stack (separate Shopify app + db + backend)
	./scripts/start-uat.sh

production: ## Bring up the PRODUCTION stack (separate Shopify app + db + backend)
	./scripts/start-production.sh

stop: ## Stop a stack (make stop ENV=uat)
	./scripts/stop-$(ENV).sh

logs: ## Tail a stack's logs (make logs ENV=uat SVC=api)
	./scripts/logs-$(ENV).sh $(SVC)

db-setup: ## Provision + migrate + seed a database (make db-setup ENV=uat)
	./scripts/db/setup.sh $(ENV)

test: ## Run the full suite in an ephemeral Postgres (no shared DB touched)
	./scripts/run-tests-isolated.sh

test-isolated: test ## Alias for `make test`

test-ui: ## Run the Playwright smoke test (needs a running/deployed app)
	cd e2e-ui && npm install && npx playwright test
