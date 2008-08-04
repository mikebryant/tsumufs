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

#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include <string.h>


const char *g_testfilename = "this.file.shouldnt.exist";

struct test_matrix {
    mode_t mode;
    int    errno_result;
};

int test_open_enoent_failures()
{
    int idx = 0;
    int fd  = 0;
    int old_errno = 0;

    struct test_matrix tests[] = {
        {O_RDONLY,          ENOENT},
        {O_WRONLY,          ENOENT},
        {O_RDONLY|O_WRONLY, ENOENT},
        {O_RDONLY|O_EXCL,   ENOENT},
        {O_WRONLY|O_EXCL,   ENOENT},
        {O_RDWR|O_EXCL,     ENOENT},
        {-1,                -1}
    };

    printf("%s [", __func__);
    fflush(stdout);

    for (idx = 0; tests[idx].mode != -1; idx++) {
        fd = open(g_testfilename, tests[idx].mode);
        old_errno = errno;

        if (fd < 0) {
            if (errno == tests[idx].errno_result) {
                printf(".");
                fflush(stdout);
                continue;
            }
        }

        printf("] fail!\n");
        fprintf(stderr, "Test index %d in %s failed.\n", idx, __func__);
        fprintf(stderr, "Errno %d: %s\n", old_errno, strerror(old_errno));

        return 0;
    }

    printf("] ok!\n");
    fflush(stdout);
    return 1;
}

int test_open_exist()
{
    int idx = 0;
    int fd  = 0;
    int old_errno = 0;

    struct test_matrix tests[] = {
        {O_RDONLY,        0},
        {O_WRONLY,        0},
        {O_RDWR,          0},
        {O_RDONLY|O_EXCL, 0},
        {O_WRONLY|O_EXCL, 0},
        {O_RDWR|O_EXCL,   0},
        {-1,              -1}
    };

    printf("%s [", __func__);
    fflush(stdout);

    fd = open(g_testfilename, O_RDWR|O_CREAT, 0644);

    if (fd < 0) {
        printf("] fail!\n");
        fprintf(stderr, "Test preparation in %s failed.\n", __func__);
        fprintf(stderr, "Errno %d: %s\n", errno, strerror(errno));
        return 0;
    }

    if (close(fd) < 0) {
        printf("] fail!\n");
        fprintf(stderr, "Test preparation in %s failed.\n", __func__);
        fprintf(stderr, "Errno %d: %s\n", errno, strerror(errno));
        return 0;
    }

    for (idx = 0; tests[idx].mode != -1; idx++) {
        fd = open(g_testfilename, tests[idx].mode);
        old_errno = errno;

        if (fd > 0) {
            printf(".");
            fflush(stdout);

            close(fd);
            continue;
        }

        printf("] fail!\n");
        fprintf(stderr, "Test index %d in %s failed.\n", idx, __func__);
        fprintf(stderr, "Errno %d: %s\n", old_errno, strerror(old_errno));

        return 0;
    }

    printf("] ok!\n");
    fflush(stdout);
    return 1;
}

int test_open_create()
{
    int idx = 0;
    int fd  = 0;
    int old_errno = 0;

    struct test_matrix tests[] = {
        {O_RDONLY|O_CREAT,         0},
        {O_WRONLY|O_CREAT,         0},
        {O_RDWR|O_CREAT,           0},
        {O_RDONLY|O_CREAT|O_EXCL,  0},
        {O_WRONLY|O_CREAT|O_EXCL,  0},
        {O_RDWR|O_CREAT|O_EXCL,    0},
        {-1,                      -1}
    };

    printf("%s [", __func__);
    fflush(stdout);

    for (idx = 0; tests[idx].mode != -1; idx++) {
        fd = open(g_testfilename, tests[idx].mode);
        old_errno = errno;

        if (fd > 0) {
            printf(".");
            fflush(stdout);

            close(fd);
            unlink(g_testfilename);
            continue;
        }

        printf("] fail!\n");
        fprintf(stderr, "Test index %d in %s failed.\n", idx, __func__);
        fprintf(stderr, "Errno %d: %s\n", old_errno, strerror(old_errno));

        return 0;
    }

    printf("] ok!\n");
    fflush(stdout);
    return 1;
}

int test_create_already_exists()
{
    int fd  = open(g_testfilename, O_CREAT | O_RDWR, 0644);
    int fd2 = open(g_testfilename, O_CREAT | O_EXCL | O_RDWR, 0644);

    printf("%s [.", __func__);
    fflush(stdout);

    if (fd < 0) {
        printf("] fail!\n");
        perror("Unable to open testme.txt for writing");
        return 0;
    }

    if (fd2 > 0) {
        printf("] fail!\n");
        perror("Second open did not return an error");
        return 0;
    }

    if (errno != EEXIST) {
        printf("] fail!\n");
        perror("Second open did not return EEXIST");
        return 0;
    }

    if (close(fd) < 0) {
        printf("] fail!\n");
        perror("Unable to close fd");
        return 0;
    }

    printf("] ok!\n");
    fflush(stdout);

    return 1;
}

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

int main(void)
{
    while (!connected()) {
        printf("Waiting for tsumufs to mount.\n");
        sleep(1);
    }
    printf("Mounted.\n");
    sleep(1);

    if (!test_open_enoent_failures()) return 1;
    if (!test_open_create()) return 1;
    if (!test_open_exist()) return 1;
    if (!test_create_already_exists()) return 1;

    return 0;
}
