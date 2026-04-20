"""cmake-ctl package entry point for -m execution."""

from importlib import import_module

main = import_module("cmake-ctl.cli").main

if __name__ == "__main__":
    raise SystemExit(main())
