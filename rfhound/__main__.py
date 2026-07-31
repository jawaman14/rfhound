"""Allow ``python -m rfhound``."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
