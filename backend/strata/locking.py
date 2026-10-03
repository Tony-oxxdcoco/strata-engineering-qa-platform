"""Non-blocking single-worker lock on macOS/Linux and native Windows."""
import os


def lock_worker(stream):
    if os.name == "nt":
        import msvcrt
        stream.seek(0)
        # locking may extend beyond EOF; the stable first byte is the lock range.
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)


def unlock_worker(stream):
    if os.name == "nt":
        import msvcrt
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream, fcntl.LOCK_UN)
