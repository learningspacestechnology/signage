#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def check_local_settings():
    """Explain the one thing a fresh clone is missing.

    `advertising/settings.py` is not tracked in git — it holds this machine's
    local configuration and credentials. Without this check the failure is a bare
    ModuleNotFoundError that gives no hint that a template exists.
    """
    if os.environ.get('DJANGO_SETTINGS_MODULE', 'advertising.settings') != \
            'advertising.settings':
        return  # An explicit override, e.g. advertising.screenshot_settings.

    here = os.path.dirname(os.path.abspath(__file__))
    if os.path.exists(os.path.join(here, 'advertising', 'settings.py')):
        return

    sys.exit(
        "advertising/settings.py is missing.\n\n"
        "It holds this checkout's local configuration and is deliberately not\n"
        "tracked in git. Create it from the template:\n\n"
        "    cp advertising/settings.sample.py advertising/settings.py\n\n"
        "The defaults in the template are enough to start the app.\n"
        "See CLAUDE.md, \"Settings\", for what each layer is for.\n"
    )


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'advertising.settings')
    check_local_settings()
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
