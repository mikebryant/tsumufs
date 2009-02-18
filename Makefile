# Copyright (C) 2008  Google, Inc. All Rights Reserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

PY_MODULES     := $(wildcard lib/tsumufs/*.py)
PY_OS_MOCKS    := $(wildcard lib/*.py)
PY_SOURCE      := $(wildcard src/*.py)
PY_UNIT_TESTS  := $(wildcard tests/unit/*_test.py)
FUNC_TEST_SRC  := $(wildcard tests/functional/*.c)
FUNC_TESTS     := $(shell echo $(FUNC_TEST_SRC) |sed -e 's/\.c//g')
UMOUNT_CMD     := sudo umount
FUMOUNT_CMD    := fusermount -u

TEST_DIR       := /tmp/tsumufs-test-dir
TEST_CACHE_DIR := /tmp/tsumufs-cache-dir
TEST_NFS_DIR   := /tmp/tsumufs-nfs-dir

PYTHON   := $(shell which python)
DESTDIR  := /
BUILDDIR := $(CURDIR)/debian/tsumufs
PROJECT  := tsumufs

DEBUG_LEVEL := 0

ifndef PYCHECKER
PYCHECKER := /usr/bin/pychecker
endif

ifndef SVN_USER
SVN_USER := $(shell echo $$USER)
endif

ifndef VERSION
VERSION := $(shell cat lib/tsumufs/__init__.py \
				|grep __version__ \
				|sed -e 's/.*= (//' -e 's/)//' -e 's/, /./g')
endif

ifdef TEST_ONLY
FUNC_TESTS := $(TEST_ONLY)
endif

ifndef CHK_SOURCES
CHK_SOURCES := $(wildcard tests/functional/*.[ch])
endif

DIST_FILENAME := tsumufs-$(VERSION).tar.gz

all: targets

install:
	$(PYTHON) setup.py install --root $(DESTDIR) $(COMPILE)

builddeb:
	mkdir -p $(BUILDDIR)
	DESTDIR=$(BUILDDIR) dpkg-buildpackage -rfakeroot

test-environment:
	@if [ -z $(NFSHOME) ]; then \
		echo "Set NFSHOME before running this target."; \
		exit 1; \
	fi

	@if [ -z $(NFSOPTS) ]; then \
		echo "Set NFSOPTS before running this target."; \
		exit 1; \
	fi

test-run: test-environment clean $(TEST_DIR) $(TEST_CACHE_DIR) $(TEST_NFS_DIR)
	rm -rf tests/filesystem
	tar xf tests/filesystem.tar -C tests/

	src/tsumufs -d -l $(DEBUG_LEVEL) -O $(NFSOPTS) \
		-o nfsmountpoint=$(TEST_NFS_DIR),cachebasedir=$(TEST_CACHE_DIR) \
		$(NFSHOME) $(TEST_DIR)

	-[ ! -z $$DISPLAY ] && (cd utils; ./tsumufs-applet $(TEST_DIR))

	cd $(TEST_DIR);             \
	CACHE_DIR=$(TEST_CACHE_DIR) \
	NFS_DIR=$(TEST_NFS_DIR)     \
	TEST_DIR=$(TEST_DIR)        \
	PS1='\[\e[m\e[1;31m\][TSUMUFS]\[\e[0m\] \h:\w\$$ ' \
	bash -norc;                 \
	cd $(OLD_PWD)

	$(UMOUNT_CMD) $(TEST_DIR)

tail-logs:
	sudo tail -f /var/log/messages |grep --color "tsumufs($(USER)):"

test: unit-tests functional-tests

unit-tests:
	for i in $(PY_UNIT_TESTS); do \
		echo PYTHONPATH="./lib" python $$i; \
		PYTHONPATH="./lib" python $$i; \
	done

$(TEST_DIR):
	mkdir $(TEST_DIR)

$(TEST_CACHE_DIR):
	mkdir -p $(TEST_CACHE_DIR)
	chown $(USER):$(shell id -g) $(TEST_CACHE_DIR)

$(TEST_NFS_DIR):
	mkdir -p $(TEST_NFS_DIR)
	chown $(USER):$(shell id -g) $(TEST_CACHE_DIR)

functional-tests: test-environment clean $(FUNC_TESTS) $(TEST_DIR) $(TEST_CACHE_DIR) $(TEST_NFS_DIR)
	for test in $(FUNC_TESTS); do      \
		rm -rf tests/filesystem;       \
		tar xf tests/filesystem.tar -C tests/; \
		echo;                          \
		echo --- $$test;               \
		src/tsumufs -d -l $(DEBUG_LEVEL) -O $(NFSOPTS)   \
			-o nfsmountpoint=$(TEST_NFS_DIR),cachebasedir=$(TEST_CACHE_DIR) \
			$(NFSHOME) $(TEST_DIR);    \
		OLDCWD=$$(pwd);                \
		export CACHE_DIR=$(TEST_CACHE_DIR); \
		export NFS_DIR=$(TEST_NFS_DIR); \
		export TEST_DIR=$(TEST_DIR);   \
		cd $(TEST_DIR);                \
		if ! $$OLDCWD/$$test; then     \
			echo "!!! $$test Failed."; \
			if [ ! -z "$(TEST_ONLY)" ]; then \
				echo "Starting emergency holographic shell to examine the rubble."; \
				CACHE_DIR=$(TEST_CACHE_DIR) \
				NFS_DIR=$(TEST_NFS_DIR)     \
				TEST_DIR=$(TEST_DIR)        \
				PS1='\[\e[m\e[1;31m\][TSUMUFS]\[\e[0m\] \h:\w\$$ ' \
				bash -norc;                 \
			fi;                        \
			cd $$OLDCWD;               \
			$(UMOUNT_CMD) $(TEST_DIR); \
			$(UMOUNT_CMD) $(TEST_NFS_DIR); \
			continue;                  \
		fi;                            \
		cd $$OLDCWD;                   \
		$(UMOUNT_CMD) $(TEST_DIR);     \
		sleep 1;                       \
		$(UMOUNT_CMD) $(TEST_DIR);     \
		echo ok;                       \
		rm -rf $(TEST_CACHE_DIR)/*;    \
	done

force-shutdown:
	-$(UMOUNT_CMD) $(TEST_NFS_DIR)
	-$(UMOUNT_CMD) $(TEST_DIR)
	-PID=$$(ps ax |grep tsumufs |grep -v grep |awk '{ print $$1 }'); 	\
		[ "$$PID" != "" ] && sleep 5; 									\
		PID=$$(ps ax |grep tsumufs |grep -v grep |awk '{ print $$1 }'); \
		[ "$$PID" != "" ] && kill -KILL $$PID

check-syntax:
	gcc -o /dev/null -S $(CHK_SOURCES)

check:
	-cd lib; $(PYCHECKER) -F ../pycheckerrc tsumufs/__init__.py; cd ..
	-$(PYCHECKER) -F pycheckerrc $(PY_OS_MOCKS)
	-$(PYCHECKER) -F pycheckerrc $(PY_SOURCE)
	-$(PYCHECKER) -F pycheckerrc $(PY_UNIT_TESTS)

find-todos:
	@printf "%-32s %-3s %s\n" Filename Line Todo
	@awk 'BEGIN { for(i=0;i<80;i++) { printf "=" }; printf "\n" }'
	@find . -iname \*.py -exec grep -nH TODO '{}' ';' \
	  | awk '{ match($$0, "([^:]+):([0-9]+):[ ]*#[ ]?(.*)", a); \
               printf("% 32s % -4d %s\n", a[1], a[2], a[3]); }' \
      | grep --color -E 'TODO(.*)?:'

fixspaces:
	sed -i -r 's/^[ ]+$$//' $(PY_MODULES) $(PY_SOURCE) $(PY_TESTS)

not-mounted:
	@if mount |grep -qe '^tsumufs on'; then                          \
		echo 'make[1]: *** TsumuFS is currently mounted. Aborting.'; \
		exit 1;                                                      \
	fi

clean: not-mounted src/tsumufs
	find . -iname \*.pyc -delete
	rm -f $(DIST_FILENAME)
	rm -f $(FUNC_TESTS)
	rm -rf $(TEST_DIR) $(TEST_CACHE_DIR)
	-rmdir $(TEST_NFS_DIR)
	-fakeroot debian/rules clean
	$(PYTHON) setup.py clean
	rm -rf build/ dist/ MANIFEST

mrclean: clean
	find . -iname \*~ -exec rm -rf '{}' ';' -prune

tag:
	svn cp https://tsumufs.googlecode.com/svn/trunk \
           https://tsumufs.googlecode.com/svn/tags/$(VERSION) \
           --username $(SVN_USER)

targets:
	@echo Targets available:
	@cat Makefile |grep -e '^[a-zA-Z-]*:' |sed 's/:/\t/' |awk '{ print "\t" $$1 }'

$(DIST_FILENAME):
	svn export http://tsumufs.googlecode.com/svn/tags/$(VERSION) /tmp/tsumufs-$(VERSION)
	tar -C /tmp/tsumufs-$(VERSION) -zcvf $(DIST_FILENAME) .
	rm -rf /tmp/tsumufs-$(VERSION)

dist: $(DIST_FILENAME)

.PHONY: all test test-environment unit-tests functional-tests \
		check fixspaces clean mrclean dist tag \
		test-run tail-logs force-shutdown find-todos
