# Makefile for odin-bots Python package

.PHONY: help install install-dev install-blst build clean publish-test publish test lint

help:
	@echo "odin-bots development commands:"
	@echo ""
	@echo "  make install       Install package in current environment"
	@echo "  make install-dev   Install package with dev dependencies"
	@echo "  make build         Build sdist and wheel distributions"
	@echo "  make clean         Remove build artifacts"
	@echo "  make test          Run pytest"
	@echo "  make install-blst  Install blst for IC certificate verification"
	@echo "  make publish-test  Upload to TestPyPI"
	@echo "  make publish       Upload to PyPI (production)"
	@echo ""

# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------

install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"

BLST_VERSION ?= v0.3.16
BLST_COMMIT  ?= e7f90de551e8df682f3cc99067d204d8b90d27ad

install-blst:
	@echo "Installing blst $(BLST_VERSION) from source..."
	$(eval BLST_DIR := $(shell mktemp -d))
	git clone --branch $(BLST_VERSION) --depth 1 https://github.com/supranational/blst $(BLST_DIR)
	@cd $(BLST_DIR) && \
		ACTUAL=$$(git rev-parse HEAD) && \
		if [ "$$ACTUAL" != "$(BLST_COMMIT)" ]; then \
			echo "ERROR: commit mismatch! expected $(BLST_COMMIT), got $$ACTUAL"; \
			rm -rf $(BLST_DIR); \
			exit 1; \
		fi
	cd $(BLST_DIR)/bindings/python && python3 run.me || true
	cp $(BLST_DIR)/bindings/python/blst.py \
		$$(python3 -c "import sysconfig; print(sysconfig.get_paths()['purelib'])")/
	cp $(BLST_DIR)/bindings/python/_blst*.so \
		$$(python3 -c "import sysconfig; print(sysconfig.get_paths()['platlib'])")/
	rm -rf $(BLST_DIR)
	@python3 -c "import blst; print('✓ blst installed successfully')"

# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------

build: clean
	pip install --quiet build
	python -m build

clean:
	rm -rf dist/
	rm -rf src/*.egg-info/
	rm -rf build/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

# ---------------------------------------------------------------------------
# Publishing
# ---------------------------------------------------------------------------

publish-test: build
	pip install --quiet twine
	twine upload --config-file .pypirc --repository testpypi dist/*

publish: build
	pip install --quiet twine
	twine upload --config-file .pypirc dist/*

# ---------------------------------------------------------------------------
# Development
# ---------------------------------------------------------------------------

test:
	pytest -v

lint:
	@echo "No linter configured yet"
