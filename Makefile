PY_MODULES := $(wildcard lib/tsumufs/*.py)
PY_SOURCE  := $(wildcard src/*.py)
PY_UNIT_TESTS := $(wildcard tests/unit/*.py)
PY_FUNC_TESTS := $(wildcard tests/functional/*.py)

PYCHECKER  := /usr/bin/pychecker

all: check test

test: unit-tests functional-tests

unit-tests:
	PYTHONPATH="./lib" python $(PY_UNIT_TESTS)

functional-tests:
	PYTHONPATH="./lib" python $(PY_FUNC_TESTS)

check:
	cd lib; $(PYCHECKER) -F ../pycheckerrc tsumufs/__init__.py; cd ..
	$(PYCHECKER) -F pycheckerrc $(PY_SOURCE)
	$(PYCHECKER) -F pycheckerrc $(PY_TESTS)

fixspaces:
	sed -i -r 's/^[ ]+$$//' $(PY_MODULES) $(PY_SOURCE) $(PY_TESTS)

clean:
	find -iname \*.pyc -exec rm -f '{}' ';'

mrclean: clean
	find -iname \*~ -exec rm -rf '{}' ';' -prune

.PHONY: all test unit-tests functional-tests check fixspaces clean mrclean
