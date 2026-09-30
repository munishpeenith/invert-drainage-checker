"""invert check <pdf> --regime {adoption,private} [--location-class ...] [--dry-run]

The regime is never inferred. Neither is the location class. Both are supplied
by the user or the checks that need them report as not checked.
"""

import argparse


def build_parser() -> argparse.ArgumentParser:
    raise NotImplementedError


def main(argv: list[str] | None = None) -> int:
    raise NotImplementedError


if __name__ == "__main__":
    raise SystemExit(main())
