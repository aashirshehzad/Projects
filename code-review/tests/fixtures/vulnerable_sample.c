/* Deliberate triggers for C-001..C-006. Parsed only, never compiled/run. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define API_KEY "abc123xyz999_not_real"           /* C-003 */

char *g_password = "hunter2xyz";                  /* C-003 */

void read_input(char *buf) {
    gets(buf);                                     /* C-001 */
}

void copy_name(char *dst, const char *src) {
    strcpy(dst, src);                              /* C-001 */
}

void log_message(const char *user_input) {
    printf(user_input);                            /* C-002 */
}

void run_backup(const char *path) {
    char cmd[256];
    sprintf(cmd, "tar czf backup.tgz %s", path);    /* C-001 */
    system(cmd);                                    /* C-004 */
}

int make_token(void) {
    int session_token = rand();                     /* C-005 */
    return session_token;
}

char *scratch(int n) {
    return alloca(n);                                /* C-006 */
}
