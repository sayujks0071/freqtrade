import subprocess  # noqa: S404, RUF100
import sys
import time

from tests.conftest import is_mac


MAXIMUM_STARTUP_TIME = 1.5 if is_mac() else 1.5


def test_startup_time():
    cmd = [sys.executable, "-m", "freqtrade", "-h"]
    # warm up to generate pyc
    subprocess.run(cmd)

    start = time.time()
    subprocess.run(cmd)
    elapsed = time.time() - start
    assert elapsed < MAXIMUM_STARTUP_TIME, (
        "The startup time is too long, try to use lazy import in the command entry function"
        f" (maximum {MAXIMUM_STARTUP_TIME}s, got {elapsed}s)"
    )
