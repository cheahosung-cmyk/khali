"""Khali 진입점 (console_scripts: khali=src.main:main)."""

from __future__ import annotations

from .cli import main as _cli_main


def main() -> None:
    raise SystemExit(_cli_main())


if __name__ == "__main__":
    main()
