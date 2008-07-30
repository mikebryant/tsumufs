PY_MODULES    := $(wildcard lib/tsumufs/*.py)
PY_SOURCE     := $(wildcard src/*.py)
PY_UNIT_TESTS := $(wildcard tests/unit/*_test.py)
FUNC_TEST_SRC := $(wildcard tests/functional/*.c)
FUNC_TESTS    := $(shell echo $(FUNC_TEST_SRC) |sed -e 's/\.c//g')

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
	for i in $(PY_UNIT_TESTS); do \
		PYTHONPATH="./lib" python $$i || break; \
	done

# TODO: Make these exist and idempotent.
functional-tests: $(FUNC_TESTS)
	-mkdir test
	for test in $(FUNC_TESTS); do     \
		echo --- $$test;              \
		utils/func_setup || break;    \
		$$test || break;              \
		utils/func_teardown || break; \
		echo ok;                      \
	done
	utils/func_teardown
	rmdir test

check:
	cd lib; $(PYCHECKER) -F ../pycheckerrc tsumufs/__init__.py; cd ..
	$(PYCHECKER) -F pycheckerrc $(PY_SOURCE)
	$(PYCHECKER) -F pycheckerrc $(PY_UNIT_TESTS)

fixspaces:
	sed -i -r 's/^[ ]+$$//' $(PY_MODULES) $(PY_SOURCE) $(PY_TESTS)

clean:
	find -iname \*.pyc -exec rm -f '{}' ';'
	rm -f $(DIST_FILENAME)
	rm -f $(FUNC_TESTS)

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
