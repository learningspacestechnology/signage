"""Populate a database with the invented dataset used for documentation shots.

    DJANGO_SETTINGS_MODULE=advertising.screenshot_settings \\
        uv run python manage.py seed_help_demo_data

Refuses to run against a database that already has users, so it can't be pointed
at a real one by accident. ``capture_help_screenshots`` calls the same code
directly against its throwaway database.
"""
import json

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from helpdocs import demo_data


class Command(BaseCommand):
    help = 'Create the fictional dataset used for help screenshots.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Seed even if the database already contains users.',
        )

    def handle(self, *args, **options):
        if User.objects.exists() and not options['force']:
            raise CommandError(
                'This database already has users. Seeding is meant for an empty '
                'throwaway database — point DJANGO_SETTINGS_MODULE at '
                'advertising.screenshot_settings, or pass --force if you are '
                'certain.'
            )

        ids = demo_data.seed()
        self.stdout.write(self.style.SUCCESS('Seeded demo data.'))
        self.stdout.write(json.dumps(ids, indent=2))
