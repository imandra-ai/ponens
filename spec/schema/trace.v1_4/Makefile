.PHONY: help
help:  ## Show this help (usage: make help)
	@echo "Usage: make [recipe]"
	@echo "Recipes:"
	@awk '/^[a-zA-Z0-9_.-]+:.*?##/ { \
		helpMessage = match($$0, /## (.*)/); \
		if (helpMessage) { \
			recipe = $$1; \
			sub(/:/, "", recipe); \
			printf "  \033[36m%-20s\033[0m %s\n", recipe, substr($$0, RSTART + 3, RLENGTH); \
		} \
	}' $(MAKEFILE_LIST)

SCRIPT_DIR := ../../../scripts

.PHONY: check-schema
check-schema:  ## Check the schema
	uv run $(SCRIPT_DIR)/extract_md_cb.py *.md -p iml | codelogician-lite check -

.PHONY: schema.iml
schema.iml:  ## Extract the schema
	uv run $(SCRIPT_DIR)/extract_md_cb.py *.md -p iml > schema.iml

.PHONY: concrete_schema.iml
concrete_schema.iml: schema.iml concretize.iml  ## Generate the concrete schema
	uv run --script $(SCRIPT_DIR)/concretize_schema.py schema.iml concretize.iml \
	> concrete_schema.iml

.PHONY: check-concrete-schema
check-concrete-schema: concrete_schema.iml  ## Check the concrete schema
	codelogician-lite check concrete_schema.iml

JSONSCHEMA_OF_TYPE_DIR := ../../../scripts/jsonschema-of-type

.PHONY: schema.json
schema.json: concrete_schema.iml  ## Generate JSON schema from concrete schema
	cd $(JSONSCHEMA_OF_TYPE_DIR) && dune exec -- jsonschema-of-type \
		$(CURDIR)/concrete_schema.iml > $(CURDIR)/schema.json
