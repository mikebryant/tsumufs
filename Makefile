PY_MODULES    := $(wildcard lib/tsumufs/*.py)
PY_SOURCE     := $(wildcard src/*.py)
PY_UNIT_TESTS := $(wildcard tests/unit/*_test.py)
PY_FUNC_TESTS := $(wildcard tests/functional/*_test.sh)

PYCHECKER := /usr/bin/pychecker

ifndef SVN_USER
SVN_USER = $(shell echo $$USER)
endif

ifndef VERSION
VERSION = $(shell cat lib/tsumufs/__init__.py \
				|grep __version__ \
				|sed -e 's/.*= (//' -e 's/)//' -e 's/, /./g')
endif

DIST_FILENAME := tsumufs-$(VERSION).tar.gz

all: check test

test: unit-tests functional-tests

unit-tests:
	PYTHONPATH="./lib" python $(PY_UNIT_TESTS)

# TODO: Make these exist and idempotent.
functional-tests:

check:
	cd lib; $(PYCHECKER) -F ../pycheckerrc tsumufs/__init__.py; cd ..
	$(PYCHECKER) -F pycheckerrc $(PY_SOURCE)
	$(PYCHECKER) -F pycheckerrc $(PY_UNIT_TESTS)

fixspaces:
	sed -i -r 's/^[ ]+$$//' $(PY_MODULES) $(PY_SOURCE) $(PY_TESTS)

clean:
	find -iname \*.pyc -exec rm -f '{}' ';'
	rm -f $(DIST_FILENAME)

mrclean: clean
	find -iname \*~ -exec rm -rf '{}' ';' -prune

tag:
	svn cp https://tsumufs.googlecode.com/svn/trunk \
           https://tsumufs.googlecode.com/svn/tags/$(VERSION) \
           --username $(SVN_USER)

$(DIST_FILENAME):
	svn export http://tsumufs.googlecode.com/svn/tags/$(VERSION) /tmp/tsumufs-$(VERSION)
	tar -C /tmp/tsumufs-$(VERSION) -zcvf $(DIST_FILENAME) .
	rm -rf /tmp/tsumufs-$(VERSION)

dist: $(DIST_FILENAME)

.PHONY: all test unit-tests functional-tests check fixspaces clean mrclean dist tag
