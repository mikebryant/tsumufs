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

#ifndef _TESTHELPERS_H
#define _TESTHELPERS_H

#define TEST_START()                            \
    printf("%s [", __func__);                   \
    fflush(stdout)

#define TEST_OK()                               \
    printf(".");                                \
    fflush(stdout)

#define TEST_FAIL()                             \
    printf("!");                                \
    fflush(stdout);

#define TEST_COMPLETE_OK()                      \
    printf("] ok!\n");                          \
    fflush(stdout);                             \
    return 1

#define TEST_COMPLETE_FAIL(str, args...)        \
    printf("] fail!\n");                        \
    printf(str, args);                          \
    fflush(stdout);                             \
    return 0

#endif
