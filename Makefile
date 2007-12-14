PY_MODULES := $(wildcard lib/tsumufs/*.py)
PY_SOURCE  := $(wildcard src/*.py)
PY_TESTS   := $(wildcard tests/*.py)

all: check test

test:
	PYTHONPATH="./lib" python $(PY_TESTS)

check:
	pychecker lib/tsumufs/__init__.py
	pychecker $(PY_SOURCE)
	pychecker $(PY_TESTS)

clean:
	find -iname \*.pyc -exec rm -f '{}' ';'

mrclean: clean
	find -iname \*~ -exec rm -rf '{}' ';' -prune

.PHONY: all test check clean mrclean
