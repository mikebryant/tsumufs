#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>

#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include <string.h>

int test_single_write(void)
{
    char *output = "Zorba!\n";
    int fd = open("test/testme.txt", O_CREAT|O_RDWR, 0644);
    int total = 0;
    int result = 0;

    if (fd < 0) {
        printf("Failed at %d\n", __LINE__);
        perror("Unable to create file testme.txt");
        return 0;
    }

    while (total < strlen(output)) {
        result = write(fd, output + result, strlen(output));

        if (result < 0) {
            printf("Failed at %d\n", __LINE__);
            perror("Unable to write to file testme.txt");
            close(fd);
            return 0;
        }

        total += result;
    }
    
    if (close(fd) < 0) {
        printf("Failed at %d\n", __LINE__);
        perror("Unable to close testme.txt");
        return 0;
    }

    return 1;
}
        
int test_multiple_writes(void)
{
    char *output = "Zorba!\n";
    int maxcount = 5;
    int fd = open("test/testme.txt", O_CREAT|O_RDWR, 0644);
    int i = 0;
    int total = 0;
    int result = 0;

    if (fd < 0) {
        printf("Failed at %d\n", __LINE__);
        perror("Unable to create file testme.txt");
        return 0;
    }

    for (i=0; i<maxcount; i++) {
        total = 0;
        result = 0;
        
        while (total < strlen(output)) {
            result = write(fd, output + result, strlen(output));
            
            if (result < 0) {
                printf("Failed at %d\n", __LINE__);
                perror("Unable to write to file testme.txt");
                close(fd);
                return 0;
            }
            
            total += result;
        }
    }
    
    if (close(fd) < 0) {
        printf("Failed at %d\n", __LINE__);
        perror("Unable to close testme.txt");
        return 0;
    }

    return 1;
}    

int main(void)
{
    if (!test_single_write()) return 1;
    if (!test_multiple_writes()) return 1;

    return 0;
}
