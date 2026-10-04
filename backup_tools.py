"""
backup_tools.py - database backups, restore, and an activity log for The Cove RESORT.
Put this file in the same folder as resort_v2.py.
"""
import os
import sqlite3
import datetime as dt


class BackupError(Exception):
    """Raised when a backup cannot be created."""


class RestoreError(BackupError):
    """Raised when a backup cannot be restored (so `except BackupError` catches both)."""


REQUIRED_TABLES = {"users", "rooms", "guests", "bookings", "payments"}


# ------------------------------------------------------------ activity log
def log_action(log_path, user, text):
    """Append one line to the log file (append mode). Never crashes the app."""
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write("%s | %s | %s\n" % (stamp, user, text))    
    except OSError:
        pass                                    # logging must never break a booking


def read_log(log_path, limit=300):
    """Return the newest `limit` log lines, newest first."""
    if not os.path.exists(log_path):
        return []
    with open(log_path, "r", encoding="utf-8") as fh:
        lines = fh.readlines()                  # read the whole file into a list
    return [ln.rstrip("\n") for ln in reversed(lines[-limit:])]

def tail_log(log_path, limit=200, block=4096):
    """Newest `limit` lines, newest first. Reads backwards from the end with seek() and tell()."""
    if not os.path.exists(log_path):
        return []
    with open(log_path, "rb") as fh:
        fh.seek(0, 2)                    # jump to the end of the file
        pos = fh.tell()                  # file size in bytes
        data = b""
        while pos > 0 and data.count(b"\n") <= limit:
            step = min(block, pos)
            pos -= step
            fh.seek(pos)                 # move back one block
            data = fh.read(step) + data
    lines = data.decode("utf-8", errors="replace").splitlines()
    if pos > 0:
        lines = lines[1:]                # the first line may be cut in half
    return list(reversed(lines[-limit:]))
# ------------------------------------------------------------ backups
def list_backups(backup_dir, prefix="resort"):
    """Backup file names, oldest first (the timestamp in the name sorts correctly)."""
    if not os.path.isdir(backup_dir):
        return []
    return sorted(f for f in os.listdir(backup_dir)
                  if f.startswith(prefix + "_") and f.endswith(".db"))


def make_backup(conn, backup_dir, keep=5, prefix="resort"):
    """Copy the live database to backups/<prefix>_<timestamp>.db and keep only the newest `keep`.
    Returns the new file's path. Raises BackupError if anything goes wrong."""
    os.makedirs(backup_dir, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    final = os.path.join(backup_dir, f"{prefix}_{stamp}.db")
    tmp = final + ".part"                       # write here first, rename when complete
    dest = None
    failure = None
    try:
        dest = sqlite3.connect(tmp)
        conn.backup(dest)                       # safe copy even while the app is open
    except (sqlite3.Error, OSError) as e:
        failure = e
    finally:
        if dest is not None:
            dest.close()                        # must be closed before renaming on Windows

    if failure:
        if os.path.exists(tmp):
            os.remove(tmp)                      # don't leave a half-written file behind
        raise BackupError(f"Could not copy the database: {failure}") from failure

    try:
        os.rename(tmp, final)
    except OSError as e:
        raise BackupError(f"Could not finish the backup file: {e}") from e

    for old in list_backups(backup_dir, prefix)[:-keep]:    # prune the oldest ones
        try:
            os.remove(os.path.join(backup_dir, old))
        except OSError:
            pass
    return final


# ------------------------------------------------------------ restore
def check_backup(path):
    """Raise RestoreError unless `path` is a healthy Cove RESORT database."""
    if not os.path.exists(path):
        raise RestoreError("That backup file no longer exists.")
    src = None
    try:
        src = sqlite3.connect(path)
        verdict = src.execute("PRAGMA integrity_check").fetchone()[0]
        tables = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    except sqlite3.Error as e:
        raise RestoreError(f"That file is not a readable database: {e}") from e
    finally:
        if src is not None:
            src.close()
    if verdict != "ok":
        raise RestoreError("That backup failed its integrity check, so it was not used.")
    missing = REQUIRED_TABLES - tables
    if missing:
        raise RestoreError("That file is not a resort backup (missing: " + ", ".join(sorted(missing)) + ").")


def restore_backup(conn, backup_dir, name, keep_safety=3):
    """Replace the live data with the backup called `name`.
    A safety copy of the current data is saved first. Returns the safety copy's path."""
    path = os.path.join(backup_dir, os.path.basename(name))     # basename: never leave the folder
    check_backup(path)
    safety = make_backup(conn, backup_dir, keep=keep_safety, prefix="safety")
    src = None
    try:
        src = sqlite3.connect(path)
        src.backup(conn)                        # copies into the open connection the app already uses
    except sqlite3.Error as e:
        raise RestoreError(f"Restore failed: {e}. Your previous data is saved in "
                           f"{os.path.basename(safety)}.") from e
    finally:
        if src is not None:
            src.close()
    return safety