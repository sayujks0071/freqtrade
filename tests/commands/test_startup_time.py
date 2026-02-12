import subprocess  # noqa: S404, RUF100
import time
import platform
from tests.conftest import is_mac

def is_windows() -> bool:
    return platform.system() == "Windows"

# Increase timeout generally for CI environments which can be slow
# Windows needs significantly more time due to process creation overhead
MAXIMUM_STARTUP_TIME = 0.7 if is_mac() else 2.5 if is_windows() else 1.5


def test_startup_time():
    # warm up to generate pyc
    subprocess.run(["freqtrade", "-h"])

    start = time.time()
    subprocess.run(["freqtrade", "-h"])
    elapsed = time.time() - start
    assert elapsed < MAXIMUM_STARTUP_TIME, (
        "The startup time is too long, try to use lazy import in the command entry function"
        f" (maximum {MAXIMUM_STARTUP_TIME}s, got {elapsed}s)"
    )
