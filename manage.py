#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import subprocess
import sys
from pathlib import Path


def main():
    """Run administrative tasks."""
    base_dir = Path(__file__).resolve().parent

    # Auto-switch to project virtual environment if invoked via global python/py
    venv_python = base_dir / ".venv" / "Scripts" / "python.exe"
    if not venv_python.exists():
        venv_python = base_dir / ".venv" / "bin" / "python"

    if venv_python.exists():
        try:
            current_exe = Path(sys.executable).resolve()
            target_exe = venv_python.resolve()
            if current_exe != target_exe:
                result = subprocess.run([str(target_exe), *sys.argv], cwd=str(base_dir))
                sys.exit(result.returncode)
        except Exception:
            pass

    sys.path.insert(0, str(base_dir))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
