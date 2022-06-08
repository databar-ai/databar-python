PN := databar
LINT_TARGET := setup.py src/ tests/
MYPY_TARGET := src/${PN} tests/


.PHONY: develop
develop:
	@python -m pip install --upgrade pip setuptools wheel
	@python -m pip install -e .[develop]


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
