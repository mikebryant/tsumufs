#include <sys/types.h>
#include <sys/stat.h>
#include <sys/xattr.h>
#include <fcntl.h>

#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include <string.h>

int test_create()
{
    int fd = open("test/testme.txt", O_CREAT | O_RDWR, 0644);

    if (fd < 0) {
        perror("Unable to open testme.txt for writing");
        return 0;
    }

    if (close(fd) < 0) {
        perror("Unable to close testme.txt");
        return 0;
    }

    return 1;
}

int test_create_already_exists()
{
    int fd = open("test/testme.txt", O_CREAT | O_RDWR, 0644);
    int fd2 = open("test/testme.txt", O_CREAT | O_EXCL | O_RDWR, 0644);

    if (fd < 0) {
        perror("Unable to open testme.txt for writing");
        return 0;
    }

    if (fd > 0) {
        perror("Second open did not return an error");
        return 0;
    }

    if (errno != EEXIST) {
        perror("Second open did not return EEXIST");
        return 0;
    }

    if (close(fd) < 0) {
        perror("Unable to close testme.txt");
        return 0;
    }

    return 1;
}

int connected(void)
{
    char *test_str = "1";
    char *buf = "   ";
    int size = 0;

    size = getxattr("test", "tsumufs.connected", buf, strlen(buf));

    if (size == -1) {
        perror("Unable to getxattr tsumufs.connected from test");
        exit(1);
    }

    printf("Got '%s', wanted '%s'\n", buf, test_str);

    if (strcmp(buf, test_str) == 0) {
        return 1;
    }

    return 0;
}

int main(void)
{
    sleep(5);
    while (!connected()) {
        printf("Waiting for tsumufs to mount.\n");
        sleep(1);
    }

    if (!test_create()) return 1;
    if (!test_create_already_exists()) return 1;

    return 0;
}
