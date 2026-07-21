.PHONY: help
help:  ## Show this help (usage: make help)
	@echo "Usage: make [recipe]"
	@echo "Recipes:"
	@awk '/^[a-zA-Z0-9_-]+:.*?##/ { \
		helpMessage = match($$0, /## (.*)/); \
		if (helpMessage) { \
			recipe = $$1; \
			sub(/:/, "", recipe); \
			printf "  \033[36m%-20s\033[0m %s\n", recipe, substr($$0, RSTART + 3, RLENGTH); \
		} \
	}' $(MAKEFILE_LIST)

# Packaging and publishing
# ====================

.PHONY: build
build:  ## Build the package
	cp ../viewer/vscode-plugin/media/visualizer.html ponens/visualizer.html || (echo "Failed to copy visualizer.html" && exit 1)
	mkdir -p ponens/demos && cp ../examples/manifest.json ponens/demos/ && \
		python3 -c "import json,shutil; m=json.load(open('../examples/manifest.json')); [shutil.copy('../examples/'+s['file'], 'ponens/demos/') for s in m['samples']]" \
		|| (echo "Failed to sync demo traces" && exit 1)
	rm -rf dist && uv build --no-sources

.PHONY: publish-testpypi
publish-testpypi: build  ## Publish to TestPyPI (test.pypi.org)
	uv publish \
	--publish-url https://test.pypi.org/legacy/ \
	-u __token__ \
	-p $$(gcloud secrets versions access --project imandra-dev --secret pypi-test-imandrax-api-api-token latest) \
	./dist/ponens-*

.PHONY: publish-pypi
publish-pypi: build  ## Publish to PyPI (pypi.org)
	uv publish \
	--publish-url https://upload.pypi.org/legacy/ \
	-u __token__ \
	-p $$(gcloud secrets versions access --project imandra-dev --secret pypi-imandrax-api-api-token latest) \
	./dist/ponens-*

.PHONY: validate-new-version
validate-new-version:
	$(eval PYPI_VER := $(shell curl -s "https://pypi.org/pypi/ponens/json" | jq '.info.version' -r))
	$(eval LOCAL_VER := $(shell grep -m1 '^version' pyproject.toml | sed -E 's/.*"([^"]+)".*/\1/'))
	@uv run python -c "lv, pv = tuple(map(int, '$(LOCAL_VER)'.split('.'))), tuple(map(int, '$(PYPI_VER)'.split('.'))); assert lv > pv" 2>/dev/null || (echo "Local $(LOCAL_VER) must be greater than PyPI $(PYPI_VER)" && exit 1)

.PHONY: release
release: validate-new-version build  ## Tag, publish to PyPI, and create a GitHub release
	@git diff --quiet || { echo "working tree dirty — commit or stash first"; exit 1; }
	$(eval VERSION := $(shell grep -m1 '^version' pyproject.toml | sed -E 's/.*"([^"]+)".*/\1/'))
	git tag -a v$(VERSION) -m "v$(VERSION)"
	git push origin v$(VERSION)
	$(MAKE) publish-pypi
	gh release create v$(VERSION) ./dist/ponens-* --generate-notes --title v$(VERSION)
