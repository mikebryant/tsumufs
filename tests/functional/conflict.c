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
#include <errno.h>
#include <string.h>

#include "testhelpers.h"


const int MAXLEN = 256;
const char *g_path_fmt = "%s/regular.file";


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

void unpause_sync(void)
{
    int result;

    result = setxattr(".", "tsumufs.pause-sync", "0", strlen("0"), XATTR_REPLACE);
    if (result < 0) {
        perror("Unable to set pause-sync.");
        exit(1);
    }
}

int test_regular_file_conflict(void)
{
    struct stat buf;
    char *fusestr = "foo";
    char *nfsstr  = "xxx";
    char *conflictpath = "./.tsumufs-conflicts/-regular.file";
    char fusepath[MAXLEN];
    char nfspath[MAXLEN];
    int bytes_written = 0;
    int result = 0;
    int old_errno = 0;
    int fd = 0;

    if (getenv("NFS_DIR") == NULL) {
        fprintf(stderr, "NFS_DIR env variable not set!\n");
        exit(1);
    }

    snprintf(fusepath, MAXLEN, g_path_fmt, ".");
    snprintf(nfspath,  MAXLEN, g_path_fmt, getenv("NFS_DIR"));
    pause_sync();

    TEST_START();

    fd = open(fusepath, O_TRUNC|O_WRONLY);
    if (fd < 0) {
        old_errno = errno;
        TEST_FAIL();
        TEST_COMPLETE_FAIL("Unable to open %s in %s\n"
                           "Errno %d: %s\n",
                           fusepath, __func__,
                           old_errno, strerror(old_errno));
    }
    TEST_OK();

    while (bytes_written < strlen(fusestr)) {
        if ((result = write(fd, fusestr + bytes_written,
                            strlen(fusestr) - bytes_written)) < 0) {
            old_errno = errno;
            TEST_FAIL();
            TEST_COMPLETE_FAIL("Unable to write to %s in %s\n"
                               "Errno %d: %s\n",
                               fusepath, __func__,
                               old_errno, strerror(old_errno));
        }

        bytes_written += result;
    }
    TEST_OK();
    close(fd);

    fd = open(nfspath, O_TRUNC|O_WRONLY);
    if (fd < 0) {
        old_errno = errno;
        TEST_FAIL();
        TEST_COMPLETE_FAIL("Unable to open %s in %s\n"
                           "Errno %d: %s\n",
                           fusepath, __func__,
                           old_errno, strerror(old_errno));
    }
    TEST_OK();

    bytes_written = 0;
    while (bytes_written < strlen(nfsstr)) {
        if ((result = write(fd, nfsstr + bytes_written,
                            strlen(fusestr) - bytes_written)) < 0) {
            old_errno = errno;
            TEST_FAIL();
            TEST_COMPLETE_FAIL("Unable to write to %s in %s\n"
                               "Errno %d: %s\n",
                               fusepath, __func__,
                               old_errno, strerror(old_errno));
        }

        bytes_written += result;
    }
    TEST_OK();
    close(fd);

    sleep(1);
    unpause_sync();
    sleep(31);

    /* if (stat(fusepath, &buf) == 0) { */
    /*     old_errno = errno; */
    /*     TEST_FAIL(); */
    /*     TEST_COMPLETE_FAIL("Stat of %s in %s succeeded\n" */
    /*                        "Errno %d: %s\n", */
    /*                        fusepath, __func__, */
    /*                        old_errno, strerror(old_errno)); */
    /* } */

    /* if (errno != ENOENT) { */
    /*     old_errno = errno; */
    /*     TEST_FAIL(); */
    /*     TEST_COMPLETE_FAIL("Stat of %s in %s resulted in" */
    /*                        "errno %d: %s\n", */
    /*                        fusepath, __func__, */
    /*                        old_errno, strerror(old_errno)); */
    /* } */

    if (stat(conflictpath, &buf) < 0) {
        old_errno = errno;
        TEST_FAIL();
        TEST_COMPLETE_FAIL("Stat of %s in %s failed\n"
                           "Errno %d: %s\n",
                           conflictpath, __func__,
                           old_errno, strerror(old_errno));
    }
    TEST_OK();

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

    if (!test_regular_file_conflict()) result = 1;

    return result;
}
