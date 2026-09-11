/*
 * Deliberately insecure sample for exercising the C/C++ side of the auditor.
 * Every block is labelled with the rule it should trigger. The SAFE block at
 * the bottom must produce NO findings.
 *
 * Try it:
 *   python -m app.main audit examples/insecure_demo.c --no-llm
 * Or drop this file (zipped) into the web UI.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <syslog.h>
#include <unistd.h>

/* ==========================================================================
 * C-003 -- Hardcoded secret assignment (HIGH)
 * ========================================================================== */
#define DB_PASSWORD "hunter2_not_a_real_password"     /* C-003 */
char *g_api_key = "abcd1234efgh5678ijkl9012";          /* C-003 */

/* ==========================================================================
 * C-001 -- Unbounded string function (CRITICAL for gets, HIGH otherwise)
 * ========================================================================== */
void read_line(char *buf) {
    gets(buf);                                          /* C-001 */
}

void copy_name(char *dst, const char *src) {
    strcpy(dst, src);                                    /* C-001 */
}

void append_suffix(char *dst, const char *suffix) {
    strcat(dst, suffix);                                 /* C-001 */
}

/* ==========================================================================
 * C-002 -- Format string vulnerability (HIGH)
 * ========================================================================== */
void log_user_message(const char *msg) {
    printf(msg);                                         /* C-002 */
}

void log_to_syslog(const char *msg) {
    syslog(LOG_INFO, msg);                               /* C-002 */
}

/* ==========================================================================
 * C-004 -- Command injection (HIGH)
 * ========================================================================== */
void run_backup(const char *path) {
    char cmd[256];
    sprintf(cmd, "tar czf backup.tgz %s", path);         /* C-001 (sprintf) */
    system(cmd);                                          /* C-004 */
}

/* ==========================================================================
 * C-005 -- Insecure randomness for a secret (MEDIUM)
 * ========================================================================== */
int make_session_token(void) {
    int session_key = rand();                             /* C-005 */
    return session_key;
}

/* ==========================================================================
 * C-006 -- Unbounded stack allocation (MEDIUM)
 * ========================================================================== */
char *scratch_buffer(int requested_size) {
    return alloca(requested_size);                        /* C-006 */
}

/* ==========================================================================
 * SAFE -- these must produce NO findings (false-positive check)
 * ========================================================================== */
const char *g_config_path = "/etc/myapp/config.pem";      /* safe: name ends with _path */

void safe_read_line(char *buf, size_t n) {
    fgets(buf, n, stdin);                                 /* safe: bounded */
}

void safe_copy_name(char *dst, size_t n, const char *src) {
    strncpy(dst, src, n);                                 /* safe: bounded */
}

void safe_log_user_message(const char *msg) {
    printf("%s", msg);                                    /* safe: literal format */
}

void safe_run_backup(const char *path) {
    char *args[] = {"tar", "czf", "backup.tgz", (char *)path, NULL};
    execv("/bin/tar", args);                               /* safe: no shell */
}

int safe_random_dice_roll(void) {
    return rand();                                         /* safe: not a security-named var */
}

char *safe_scratch_buffer(void) {
    static char buf[128];
    return buf;                                            /* safe: no alloca */
}
