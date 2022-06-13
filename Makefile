PN := databar
LINT_TARGET := setup.py src/ tests/
MYPY_TARGET := src/${PN} tests/

PYTHON := python3

.PHONY: develop
develop:
	@python -m pip install --upgrade pip setuptools wheel
	@python -m pip install -e .[develop]


.PHONY: dist
# target: dist - Build all artifacts
dist: dist-sdist dist-wheel


.PHONY: dist-sdist
# target: dist-sdist - Build sdist artifact
dist-sdist:
	@${PYTHON} setup.py sdist


.PHONY: dist-wheel
# target: dist-wheel - Build wheel artifact
dist-wheel:
	@${PYTHON} setup.py bdist_wheel


.PHONY: distcheck
# target: distcheck - Verify distributed artifacts
distcheck: distcheck-clean sdist
	@mkdir -p dist/$(PN)
	@tar -xf dist/$(PN)-$(PV).tar.gz -C dist/$(PN) --strip-components=1
	@$(MAKE) -C dist/$(PN) venv
	. dist/$(PN)/venv/bin/activate && $(MAKE) -C dist/$(PN) develop
	. dist/$(PN)/venv/bin/activate && $(MAKE) -C dist/$(PN) check
	@rm -rf dist/$(PN)


.PHONY: distcheck-clean
distcheck-clean:
	@rm -rf dist/$(PN)


.PHONY: format
format: format-black format-isort


.PHONY: format-black
format-black:
	@black ${LINT_TARGET}


.PHONY: format-isort
format-isort:
	@isort -rc ${LINT_TARGET}


.PHONY: help
# target: help - Print this help
help:
	@egrep "^# target: " Makefile \
		| sed -e 's/^# target: //g' \
		| sort -h \
		| awk '{printf("    %-16s", $$1); $$1=$$2=""; print "-" $$0}'


.PHONY: install
# target: install - Install the project
install:
	@pip install .


.PHONY: lint
# target: lint - Check source code with linters
lint: lint-isort lint-black lint-flake8 lint-mypy lint-pylint


.PHONY: lint-black
lint-black:
	@python -m black --check --diff ${LINT_TARGET}


.PHONY: lint-flake8
lint-flake8:
	@python -m flake8 --statistics ${LINT_TARGET}


.PHONY: lint-isort
lint-isort:
	@python -m isort.main -df -c -rc ${LINT_TARGET}


.PHONY: lint-mypy
lint-mypy:
	@python -m mypy ${MYPY_TARGET}


.PHONY: lint-pylint
lint-pylint:
	@python -m pylint --rcfile=.pylintrc --errors-only ${LINT_TARGET}


.PHONY: test
test:
	@python -m coverage run -m py.test
	@python -m coverage report

venv:
	@python3 -m venv venv

.PHONY: clean
# target: clean - Remove intermediate and generated files
clean:
	@${PYTHON} setup.py clean
	@find . -type f -name '*.py[co]' -delete
	@find . -type d -name '__pycache__' -delete
	@rm -rf {build,htmlcov,cover,coverage,dist,.coverage,.hypothesis}
	@rm -rf src/*.egg-info
	@rm -f VERSION

.PHONY: check-docs
check-docs:
	@# Doesn't generate any output but prints out errors and warnings.
	make -C docs dummy

.PHONY: docs
docs:
	make -C docs html
