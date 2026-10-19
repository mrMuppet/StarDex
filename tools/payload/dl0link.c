/*
 * dl0link.bin - GoldHEN payload (BinLoader, port 9090) for SingStar (CUSA00033):
 * creates /download0/Pack0.psarc -> /av_contents/video/ss/Pack0.psarc inside the running game's sandbox,
 * so the disc-song loader (only accepts /download0/ paths, download0 = fixed 1 GiB image) reads the pack from
 * the big user partition (FTP: /user/av_contents/video/ss/Pack0.psarc). See docs/TECHNIK.md.
 *
 * Freestanding: only raw syscalls, no libraries. Root/escape via GoldHEN SDK (syscall 500, cmd 2 = jailbreak).
 * SingStar must be running (download0 is only mounted then). An existing real Pack0.psarc in download0 is
 * renamed to Pack0.psarc.bak, never deleted.
 */
typedef unsigned long u64;
typedef unsigned int u32;
typedef unsigned short u16;

#define SYS_write 4
#define SYS_open 5
#define SYS_close 6
#define SYS_unlink 10
#define SYS_symlink 57
#define SYS_readlink 58
#define SYS_rename 128
#define SYS_mkdir 136
#define SYS_stat 188
#define SYS_lstat 190
#define GOLDHEN_SYS 500
#define GH_KLOG 1
#define GH_JAILBREAK 2
#define GH_UNJAILBREAK 3

#define S_IFMT 0170000
#define S_IFLNK 0120000
#define S_IFREG 0100000
#define O_WRONLY 1
#define EEXIST 17

static const char SANDBOX[] = "/mnt/sandbox/CUSA00033_000/download0";
static const char LINK[] = "/mnt/sandbox/CUSA00033_000/download0/Pack0.psarc";
static const char BAK[] = "/mnt/sandbox/CUSA00033_000/download0/Pack0.psarc.bak";
static const char TARGET[] = "/av_contents/video/ss/Pack0.psarc";   /* as the game sees it */
static const char EXT_DIR[] = "/user/av_contents/video/ss";         /* same folder, real root */

/* FreeBSD syscall: returns result, or -errno on error (carry flag) */
static long sc(long n, long a1, long a2, long a3, long a4) {
    long ret;
    unsigned char cf;
    register long r10 __asm__("r10") = a4;
    __asm__ volatile("syscall; setc %1"
                     : "=a"(ret), "=r"(cf), "+D"(a1), "+S"(a2), "+d"(a3), "+r"(r10)
                     : "a"(n)
                     : "rcx", "r8", "r9", "r11", "memory");
    return cf ? -ret : ret;
}

/* syscall 0 = indirect syscall: number in rdi */
static long gh(long cmd, void *data) { return sc(0, GOLDHEN_SYS, cmd, (long)data, 0); }

struct jb_backup {
    u32 cr_uid, cr_ruid, cr_rgid, cr_groups;
    u64 cr_paid, cr_caps[2];
    void *cr_prison, *fd_cdir, *fd_jdir, *fd_rdir;
};

static u64 slen(const char *s) { u64 n = 0; while (s[n]) n++; return n; }
static int seq(const char *a, const char *b) { while (*a && *a == *b) { a++; b++; } return *a == *b; }
static char *cat(char *d, const char *s) { while (*s) *d++ = *s++; *d = 0; return d; }
static char *num(char *d, long v) {
    char t[24]; int i = 0;
    if (v < 0) { *d++ = '-'; v = -v; }
    do { t[i++] = '0' + v % 10; v /= 10; } while (v);
    while (i) *d++ = t[--i];
    *d = 0;
    return d;
}

/* PS4 notification: what sceKernelSendNotificationRequest does - write the request to /dev/notification0 */
struct notify_req {
    int type, req_id, priority, msg_id, target_id, user_id, unk1, unk2, app_id, error_num, unk3;
    char use_icon_uri;
    char message[1024];
    char icon_uri[1024];
    char unk[1024];
};

static void notify(const char *msg) {
    struct notify_req r;
    char *p = (char *)&r;
    for (u64 i = 0; i < sizeof r; i++) p[i] = 0;
    r.target_id = -1;
    r.use_icon_uri = 1;
    cat(r.message, msg);
    cat(r.icon_uri, "cxml://psnotification/tex_icon_system");
    long fd = sc(SYS_open, (long)"/dev/notification0", O_WRONLY, 0, 0);
    if (fd >= 0) {
        sc(SYS_write, fd, (long)&r, sizeof r, 0);
        sc(SYS_close, fd, 0, 0, 0);
    }
    gh(GH_KLOG, (void *)msg);
}

static int run(char *msg) {
    unsigned char st[120];            /* struct stat: st_mode u16 @8, st_size i64 @72 */
    char buf[128];
    char *m = msg;
    long r;

    if (sc(SYS_stat, (long)SANDBOX, (long)st, 0, 0) < 0) {
        cat(m, "SingStar-Link: zuerst SingStar starten (download0 nicht eingehaengt)");
        return 1;
    }
    r = sc(SYS_mkdir, (long)EXT_DIR, 0777, 0, 0);
    if (r < 0 && r != -EEXIST) {
        m = cat(m, "SingStar-Link: Ordner anlegen fehlgeschlagen, Fehler ");
        num(m, -r);
        return 1;
    }
    if (sc(SYS_lstat, (long)LINK, (long)st, 0, 0) >= 0) {
        u16 mode = *(u16 *)(st + 8);
        long size = *(long *)(st + 72);
        if ((mode & S_IFMT) == S_IFLNK) {
            r = sc(SYS_readlink, (long)LINK, (long)buf, sizeof buf - 1, 0);
            if (r > 0) {
                buf[r] = 0;
                if (seq(buf, TARGET)) {
                    cat(m, "SingStar-Link ist schon eingerichtet");
                    return 0;
                }
            }
            sc(SYS_unlink, (long)LINK, 0, 0, 0);       /* link with another target */
        } else if ((mode & S_IFMT) == S_IFREG && size == 0) {
            sc(SYS_unlink, (long)LINK, 0, 0, 0);       /* empty placeholder */
        } else {
            sc(SYS_unlink, (long)BAK, 0, 0, 0);        /* old backup of an earlier run */
            r = sc(SYS_rename, (long)LINK, (long)BAK, 0, 0);
            if (r < 0) {
                m = cat(m, "SingStar-Link: altes Pack0.psarc nicht umbenennbar, Fehler ");
                num(m, -r);
                return 1;
            }
        }
    }
    r = sc(SYS_symlink, (long)TARGET, (long)LINK, 0, 0);
    if (r < 0) {
        m = cat(m, "SingStar-Link: symlink fehlgeschlagen, Fehler ");
        num(m, -r);
        return 1;
    }
    cat(m, "SingStar-Link eingerichtet. Pack nach /user/av_contents/video/ss/Pack0.psarc, SingStar neu starten");
    return 0;
}

__attribute__((section(".text.entry"))) int _start(void) {
    struct jb_backup jb;
    char msg[256];
    msg[0] = 0;
    if (gh(GH_JAILBREAK, &jb) != 0) {
        notify("SingStar-Link: GoldHEN-Jailbreak fehlgeschlagen (GoldHEN 2.x noetig)");
        return 1;
    }
    int rc = run(msg);
    notify(msg);
    gh(GH_UNJAILBREAK, &jb);
    return rc;
}
