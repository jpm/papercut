test:
	python -m pytest

# needs Docker; see docs/integration-testing-plan.md
test-integration:
	docker compose -f docker-compose.test.yml run --rm papercut
	docker compose -f docker-compose.test.yml down -v

.PHONY: test test-integration
