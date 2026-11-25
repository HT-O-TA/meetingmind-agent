"""Use synthetic Agent answers while preserving real HTTP and SSE boundaries."""
import os
import sys

from bench_local_business import BOOTSTRAP

if __name__ == "__main__":
    sys.argv.append("8000")
    exec(BOOTSTRAP.replace("sleep(0.25)", "sleep(12)").replace('host="127.0.0.1"', 'host="0.0.0.0"'))
