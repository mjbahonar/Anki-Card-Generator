"""Compatibility entry point. V4 settings are in config.toml; prefer main.py."""
from main import main
if __name__ == '__main__':
    raise SystemExit(main())
