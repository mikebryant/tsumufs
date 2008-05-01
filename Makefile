PY_MODULES := $(wildcard lib/tsumufs/*.py)
PY_SOURCE  := $(wildcard src/*.py)
PY_TESTS   := $(wildcard tests/*.py)

PYCHECKER  := /usr/bin/pychecker

all: check test

test:
	PYTHONPATH="./lib" python $(PY_TESTS)

check:
	cd lib; $(PYCHECKER) -F ../pycheckerrc tsumufs/__init__.py; cd ..
	$(PYCHECKER) -F pycheckerrc $(PY_SOURCE)
	$(PYCHECKER) -F pycheckerrc $(PY_TESTS)

clean:
	find -iname \*.pyc -exec rm -f '{}' ';'

mrclean: clean
	find -iname \*~ -exec rm -rf '{}' ';' -prune

.PHONY: all test check clean mrclean
