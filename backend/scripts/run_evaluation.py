#!/usr/bin/env python3
"""兼容旧命令；正式实现统一委托给 scripts/evaluate.py。"""
from evaluate import main


if __name__ == "__main__":
    raise SystemExit(main())
