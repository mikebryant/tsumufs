/*
 * Copyright (C) 2008  Google, Inc. All Rights Reserved.
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 2 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License along
 * with this program; if not, write to the Free Software Foundation, Inc.,
 * 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
 */

#include <sys/types.h>
#include <sys/stat.h>
#include <sys/xattr.h>
#include <fcntl.h>
#include <unistd.h>

#include <stdio.h>
#include <stdlib.h>
#include <dirent.h>
#include <errno.h>
#include <string.h>

#include "testhelpers.h"


const char *g_existing_dir = "dir";
const char *g_missing_dir = "this.file.shouldnt.exist";
const char *g_new_file = "this.file.shouldnt.exist/new.empty.file";
const char *g_new_file_basename = "new.empty.file";
const char *g_data = "foo bar baz\n";


int connected(void)
{
    char *test_str = "1";
    char buf[2] = " \0";
    int size = 0;

    size = getxattr(".", "tsumufs.connected", buf, strlen(buf));

    if (size == -1) {
        perror("Unable to getxattr tsumufs.connected from current directory");
        exit(1);
    }

    if (strcmp(buf, test_str) == 0) {
        return 1;
    }

    return 0;
}

void pause_sync(void)
{
    int result;

    result = setxattr(".", "tsumufs.pause-sync", "1", strlen("1"), XATTR_REPLACE);
    if (result < 0) {
        perror("Unable to set pause-sync.");
        exit(1);
    }
}

int test_dir_eexist(void)
{
    int result = 0;
    int old_errno = 0;

    TEST_START();

    result = mkdir(g_existing_dir, 0755);
    if (result < 0) {
        if (errno != EEXIST) {
            old_errno = errno;
            TEST_FAIL();
            TEST_COMPLETE_FAIL("mkdir of %s succeeded in %s\n"
                               "Errno %d: %s\n",
                               g_existing_dir, __func__,
                               old_errno, strerror(old_errno));
        }
    }
    TEST_OK();

    TEST_COMPLETE_OK();
}

int test_dir_nonexist(void)
{
    struct stat buf;
    int result = 0;
    int old_errno = 0;

    TEST_START();

    result = mkdir(g_missing_dir, 0755);
    if (result < 0) {
        old_errno = errno;
        TEST_FAIL();
        TEST_COMPLETE_FAIL("Unable to mkdir %s in %s\n"
                           "Errno %d: %s\n",
                           g_missing_dir, __func__,
                           old_errno, strerror(old_errno));
    }
    TEST_OK();

    if (stat(g_missing_dir, &buf) != 0) {
        old_errno = errno;
        TEST_FAIL();
        TEST_COMPLETE_FAIL("Unable to stat previously made dir %s in %s\n"
                           "Errno %d: %s\n",
                           g_missing_dir, __func__,
                           old_errno, strerror(old_errno));
    }
    TEST_OK();

    if ((buf.st_mode & S_IFDIR) == 0) {
        old_errno = errno;
        TEST_FAIL();
        TEST_COMPLETE_FAIL("Stat mode of %s in %s shows as not dir\n"
                           "Errno %d: %s\n"
                           "Mode was %o",
                           g_missing_dir, __func__,
                           old_errno, strerror(old_errno),
                           buf.st_mode);
    }
    TEST_OK();

    if ((buf.st_mode & 0755) != 0755) {
        old_errno = errno;
        TEST_FAIL();
        TEST_COMPLETE_FAIL("Stat mode of %s in %s shows as not 0755\n"
                           "Errno %d: %s\n"
                           "Mode was %o",
                           g_missing_dir, __func__,
                           old_errno, strerror(old_errno),
                           buf.st_mode);
    }
    TEST_OK();

    if (rmdir(g_missing_dir) != 0) {
        old_errno = errno;
        TEST_FAIL();
        TEST_COMPLETE_FAIL("Attempt to unlink %s in %s failed\n"
                           "Errno %d: %s\n",
                           g_missing_dir, __func__,
                           old_errno, strerror(old_errno));
    }
    TEST_OK();

    TEST_COMPLETE_OK();
}

int test_mkdir_with_new_file(void)
{
    int result = 0;
    int old_errno = 0;
    FILE *fp = NULL;
    DIR *dp = NULL;
    struct dirent *dir = NULL;

    TEST_START();

    result = mkdir(g_missing_dir, 0755);
    if (result < 0) {
        old_errno = errno;
        TEST_FAIL();
        TEST_COMPLETE_FAIL("mkdir of %s failed in %s\n"
                           "Errno %d: %s\n",
                           g_missing_dir, __func__,
                           old_errno, strerror(old_errno));
    }
    TEST_OK();

    fp = fopen(g_new_file, "w+");
    if (!fp) {
        old_errno = errno;
        TEST_FAIL();
        TEST_COMPLETE_FAIL("fopen(%s, 'w+') failed in %s\n"
                           "Errno %d: %s\n",
                           g_new_file, __func__,
                           old_errno, strerror(old_errno));
    }
    TEST_OK();

    result = fwrite(g_data, 1, strlen(g_data), fp);
    if (result != strlen(g_data)) {
        old_errno = errno;
        TEST_FAIL();
        TEST_COMPLETE_FAIL("fwrite to %s failed in %s\n"
                           "Errno %d: %s\n",
                           g_new_file, __func__,
                           old_errno, strerror(old_errno));
    }
    TEST_OK();

    fclose(fp);

    dp = opendir(g_missing_dir);
    if (!dp) {
        old_errno = errno;
        TEST_FAIL();
        TEST_COMPLETE_FAIL("opendir of %s failed in %s\n"
                           "Errno %d: %s\n",
                           g_missing_dir, __func__,
                           old_errno, strerror(old_errno));
    }
    TEST_OK();

    /* TODO(functionals): Make this not depend on dir ordering! */

    /* Read . */
    dir = readdir(dp);
    if (!dir) {
        old_errno = errno;
        TEST_FAIL();
        TEST_COMPLETE_FAIL("readdir of %s failed in %s: premature EOD\n"
                           "Errno %d: %s\n",
                           g_missing_dir, __func__,
                           old_errno, strerror(old_errno));
    }
    TEST_OK();

    if (strcmp(dir->d_name, ".") != 0) {
        old_errno = errno;
        TEST_FAIL();
        TEST_COMPLETE_FAIL("readdir of %s failed in %s: %s is not .\n"
                           "Errno %d: %s\n",
                           g_missing_dir, __func__, dir->d_name,
                           old_errno, strerror(old_errno));
    }
    TEST_OK();

    if (dir->d_type != DT_DIR) {
        old_errno = errno;
        TEST_FAIL();
        TEST_COMPLETE_FAIL("readdir of %s failed in %s: %s is not a directory\n"
                           "Errno %d: %s\n",
                           g_missing_dir, __func__, dir->d_name,
                           old_errno, strerror(old_errno));
    }
    TEST_OK();

    /* Read .. */
    dir = readdir(dp);
    if (!dir) {
        old_errno = errno;
        TEST_FAIL();
        TEST_COMPLETE_FAIL("readdir of %s failed in %s: premature EOD\n"
                           "Errno %d: %s\n",
                           g_missing_dir, __func__,
                           old_errno, strerror(old_errno));
    }
    TEST_OK();

    if (strcmp(dir->d_name, "..") != 0) {
        old_errno = errno;
        TEST_FAIL();
        TEST_COMPLETE_FAIL("readdir of %s failed in %s: %s is not ..\n"
                           "Errno %d: %s\n",
                           g_missing_dir, __func__, dir->d_name,
                           old_errno, strerror(old_errno));
    }
    TEST_OK();

    if (dir->d_type != DT_DIR) {
        old_errno = errno;
        TEST_FAIL();
        TEST_COMPLETE_FAIL("readdir of %s failed in %s: %s is not a directory\n"
                           "Errno %d: %s\n",
                           g_missing_dir, __func__, dir->d_name,
                           old_errno, strerror(old_errno));
    }
    TEST_OK();

    /* Read g_new_file */
    dir = readdir(dp);
    if (!dir) {
        old_errno = errno;
        TEST_FAIL();
        TEST_COMPLETE_FAIL("readdir of %s failed in %s: premature EOD\n"
                           "Errno %d: %s\n",
                           g_missing_dir, __func__,
                           old_errno, strerror(old_errno));
    }
    TEST_OK();

    if (strcmp(dir->d_name, g_new_file_basename) != 0) {
        old_errno = errno;
        TEST_FAIL();
        TEST_COMPLETE_FAIL("readdir of %s failed in %s: %s is not %s\n"
                           "Errno %d: %s\n",
                           g_missing_dir, __func__, dir->d_name,
                           g_new_file_basename, old_errno, strerror(old_errno));
    }
    TEST_OK();

    if (dir->d_type != DT_REG) {
        old_errno = errno;
        TEST_FAIL();
        TEST_COMPLETE_FAIL("readdir of %s failed in %s: %s is not a regular file\n"
                           "Errno %d: %s\n",
                           g_missing_dir, __func__, dir->d_name,
                           old_errno, strerror(old_errno));
    }
    TEST_OK();

    /* Read EOD */
    dir = readdir(dp);
    if (dir) {
        old_errno = errno;
        TEST_FAIL();
        TEST_COMPLETE_FAIL("readdir of %s succeeded in %s: expected EOD\n"
                           "Errno %d: %s\n",
                           g_missing_dir, __func__,
                           old_errno, strerror(old_errno));
    }
    TEST_OK();

    closedir(dp);

    TEST_COMPLETE_OK();
}

int main(void)
{
    int result = 0;

    while (!connected()) {
        printf("Waiting for tsumufs to mount.\n");
        sleep(1);
    }
    printf("Mounted.\n");
    sleep(1);

    pause_sync();
    sleep(1);

    if (!test_dir_eexist()) result = 1;
    if (!test_dir_nonexist()) result = 1;
    if (!test_mkdir_with_new_file()) result = 1;

    return result;
}
