/* Safe counterparts to every pattern in vulnerable_sample.c. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

const char *g_public_name = "not-a-secret-value";  /* safe: name has no secret token */

void read_input(char *buf, size_t n) {
    fgets(buf, n, stdin);                           /* safe: bounded */
}

void copy_name(char *dst, size_t n, const char *src) {
    strncpy(dst, src, n);                           /* safe: bounded */
}

void log_message(const char *user_input) {
    printf("%s", user_input);                       /* safe: literal format string */
}

void run_backup(const char *path) {
    char *args[] = {"tar", "czf", "backup.tgz", (char *)path, NULL};
    execv("/bin/tar", args);                         /* safe: no shell */
}

int make_id(void) {
    return rand();                                   /* safe: not stored in a security-named var */
}

char *scratch(void) {
    static char buf[64];
    return buf;                                      /* safe: no alloca */
}
