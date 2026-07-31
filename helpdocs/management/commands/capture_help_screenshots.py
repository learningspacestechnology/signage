"""Capture the screenshots embedded in the help documentation.

    DJANGO_SETTINGS_MODULE=advertising.screenshot_settings \\
        uv run python manage.py capture_help_screenshots

Builds a throwaway database, seeds it with invented data, serves the app
in-process, and drives a headless browser over the specs in
``helpdocs/screenshots.py``.

Two things keep this safe to re-run:

* It refuses to start unless the database lives under ``.help-capture/``, so it
  can never rebuild your development database.
* A PNG is only rewritten when it differs *materially* from the committed one,
  so pages carrying a clock don't produce a diff on every run.
"""
import io
import shutil
from pathlib import Path

from django.conf import settings
from django.contrib.auth import (
    BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY,
)
from django.contrib.auth.models import User
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.staticfiles.handlers import StaticFilesHandler
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.test.testcases import LiveServerThread

from PIL import Image, ImageChops

from helpdocs import demo_data, screenshots

OUTPUT_DIR = (
    Path(__file__).resolve().parents[2] / 'static' / 'helpdocs' / 'screenshots'
)

#: Fraction of the image that must change before a PNG is rewritten. Clocks and
#: "last seen" strings shift a handful of pixels; a real UI change shifts far
#: more than this.
DEFAULT_THRESHOLD = 0.005


class Command(BaseCommand):
    help = 'Capture help documentation screenshots with a headless browser.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--only', action='append', metavar='NAME',
            help='Capture only this shot. Repeatable.',
        )
        parser.add_argument(
            '--list', action='store_true', help='List the shot names and exit.',
        )
        parser.add_argument(
            '--threshold', type=float, default=DEFAULT_THRESHOLD,
            help=f'Change fraction required to rewrite a PNG '
                 f'(default {DEFAULT_THRESHOLD}).',
        )
        parser.add_argument(
            '--keep-db', action='store_true',
            help='Leave the capture database in place afterwards, for debugging.',
        )

    def handle(self, *args, **options):
        if options['list']:
            for shot in screenshots.SHOTS:
                self.stdout.write(f'{shot.name:24} {shot.path}')
            return

        self._guard_database()
        sync_playwright = self._import_playwright()

        selected = self._select(options['only'])
        capture_root = Path(settings.CAPTURE_ROOT)

        self.stdout.write('Building the capture database...')
        if capture_root.exists():
            shutil.rmtree(capture_root)
        capture_root.mkdir(parents=True)
        call_command('migrate', verbosity=0, interactive=False)
        ids = demo_data.seed()

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        server = LiveServerThread('127.0.0.1', StaticFilesHandler)
        server.daemon = True
        server.start()
        # The thread binds to port 0 and only learns the real port once the
        # socket is open, so `server.port` is meaningless until this returns.
        server.is_ready.wait()
        if server.error:
            raise CommandError(f'Could not start the test server: {server.error}')
        base_url = f'http://127.0.0.1:{server.port}'

        written, unchanged, failed = [], [], []
        try:
            cookies = self._session_cookies(server.port)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                try:
                    for shot in selected:
                        try:
                            changed = self._capture(
                                browser, cookies, base_url, shot, ids,
                                options['threshold'],
                            )
                        except Exception as exc:  # noqa: BLE001 — keep going
                            failed.append((shot.name, exc))
                            self.stdout.write(
                                self.style.ERROR(f'  {shot.name}: {exc}')
                            )
                            continue
                        if changed:
                            written.append(shot.name)
                            self.stdout.write(self.style.SUCCESS(
                                f'  {shot.name}: written'))
                        else:
                            unchanged.append(shot.name)
                            self.stdout.write(f'  {shot.name}: unchanged')
                finally:
                    browser.close()
        finally:
            server.terminate()
            if not options['keep_db'] and capture_root.exists():
                shutil.rmtree(capture_root, ignore_errors=True)

        self.stdout.write('')
        self.stdout.write(
            f'{len(written)} written, {len(unchanged)} unchanged, '
            f'{len(failed)} failed.'
        )
        if failed:
            raise CommandError(
                'Failed: ' + ', '.join(name for name, _ in failed)
            )

    # -- helpers -----------------------------------------------------------

    def _guard_database(self):
        name = str(settings.DATABASES['default']['NAME'])
        if '.help-capture' not in name:
            raise CommandError(
                'Refusing to run: the configured database is not a capture '
                f'database ({name}). Re-run with '
                'DJANGO_SETTINGS_MODULE=advertising.screenshot_settings — this '
                'command drops and rebuilds whatever database it is pointed at.'
            )

    def _import_playwright(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise CommandError(
                'Playwright is not installed. Install it with:\n'
                '  uv add --optional dev playwright\n'
                '  uv run playwright install --with-deps chromium'
            ) from exc
        return sync_playwright

    def _select(self, only):
        if not only:
            return list(screenshots.SHOTS)
        selected = []
        for name in only:
            shot = screenshots.get_shot(name)
            if shot is None:
                raise CommandError(
                    f'No shot named "{name}". Use --list to see them all.'
                )
            selected.append(shot)
        return selected

    def _session_cookies(self, port):
        """A ready-made session cookie per demo user.

        Minting the session directly avoids putting a password in the repository
        and avoids depending on the login form's markup, while still leaving the
        login page itself capturable as an anonymous visitor.
        """
        cookies = {}
        for role, username in (
            (screenshots.ADMIN, demo_data.ADMIN_USERNAME),
            (screenshots.OPERATOR, demo_data.OPERATOR_USERNAME),
        ):
            user = User.objects.get(username=username)
            session = SessionStore()
            session[SESSION_KEY] = str(user.pk)
            session[BACKEND_SESSION_KEY] = 'django.contrib.auth.backends.ModelBackend'
            session[HASH_SESSION_KEY] = user.get_session_auth_hash()
            session.save()
            cookies[role] = {
                'name': settings.SESSION_COOKIE_NAME,
                'value': session.session_key,
                'domain': '127.0.0.1',
                'path': '/',
            }
        return cookies

    def _capture(self, browser, cookies, base_url, shot, ids, threshold):
        width, height = shot.viewport
        context = browser.new_context(
            viewport={'width': width, 'height': height},
            device_scale_factor=2,
        )
        try:
            if shot.as_user is not None:
                context.add_cookies([cookies[shot.as_user]])
            page = context.new_page()

            url = base_url + shot.path.format(**ids)
            response = page.goto(url, wait_until='load')
            if response is not None and response.status >= 400:
                raise RuntimeError(f'{url} returned HTTP {response.status}')

            if shot.wait_for:
                page.wait_for_selector(
                    shot.wait_for, state=shot.wait_state, timeout=10_000,
                )
            for selector in shot.click:
                target = page.locator(selector).first
                if target.count():
                    target.click()
            if shot.run_js:
                page.evaluate(shot.run_js)
            page.wait_for_timeout(shot.settle_ms)

            image_bytes = None
            if shot.clip:
                element = page.locator(shot.clip).first
                if element.count():
                    image_bytes = element.screenshot()
                else:
                    self.stdout.write(self.style.WARNING(
                        f'  {shot.name}: "{shot.clip}" not found, '
                        f'capturing the viewport instead'
                    ))
            elif shot.clip_rect:
                x, y, clip_width, clip_height = shot.clip_rect
                image_bytes = page.screenshot(clip={
                    'x': x, 'y': y, 'width': clip_width, 'height': clip_height,
                })
            if image_bytes is None:
                image_bytes = page.screenshot(full_page=shot.full_page)
        finally:
            context.close()

        destination = OUTPUT_DIR / f'{shot.name}.png'
        if not _materially_different(image_bytes, destination, threshold):
            return False
        destination.write_bytes(image_bytes)
        return True


def _materially_different(new_bytes, path, threshold):
    """Whether a new capture differs enough from the committed PNG to rewrite.

    Screens carrying a clock or a "last seen" value change by a few pixels every
    run; rewriting for that would put a binary diff in every commit.
    """
    if not path.exists():
        return True
    try:
        with Image.open(path) as existing, Image.open(io.BytesIO(new_bytes)) as new:
            if existing.size != new.size:
                return True
            diff = ImageChops.difference(
                existing.convert('RGB'), new.convert('RGB'),
            )
            bbox = diff.getbbox()
            if bbox is None:
                return False
            changed = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
            total = existing.size[0] * existing.size[1]
            return (changed / total) > threshold
    except OSError:
        # Unreadable or truncated existing file — replace it.
        return True
