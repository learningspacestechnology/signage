"""Validate the help documentation against the code and the files on disk.

Run before finishing any change that touches user-facing behaviour:

    uv run python manage.py check_help_docs

Deliberately not wired into CI — it is a tool for the author (and for the
``/help-docs`` skill), not a gate. Exits non-zero on errors so it can still be
used in a script.
"""
from django.contrib import admin
from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand, CommandError

from helpdocs import registry, rendering, screenshots

#: Admin URL names that legitimately have no help page, so the coverage check
#: doesn't nag about them. Keep the reason with the entry.
COVERAGE_EXEMPT = {
    # Scheduling primitives documented as part of the Periodic Tasks page rather
    # than each having their own.
    'django_celery_beat_intervalschedule_changelist',
    'django_celery_beat_crontabschedule_changelist',
    'django_celery_beat_solarschedule_changelist',
    'django_celery_beat_clockedschedule_changelist',
    # Internal celery bookkeeping, covered in passing by the Task Results
    # section of the Periodic Tasks page.
    'django_celery_results_groupresult_changelist',
    # Registered read-only and hidden from the index; it exists only so the
    # Group/User forms can autocomplete permissions. Permissions themselves are
    # documented on the Users and teams / How access works pages.
    'auth_permission_changelist',
}


class Command(BaseCommand):
    help = 'Check help documentation for missing pages, screenshots and links.'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.errors = []
        self.warnings = []
        self._known_permissions = None

    def add_arguments(self, parser):
        parser.add_argument(
            '--strict',
            action='store_true',
            help='Treat warnings (e.g. missing screenshots) as errors.',
        )

    def handle(self, *args, **options):
        self.errors = []
        self.warnings = []

        self._known_permissions = self._load_permissions()

        self._check_intros()
        self._check_manifest_matches_disk()
        self._check_pages()
        self._check_screenshot_specs()
        self._check_admin_coverage()

        for warning in self.warnings:
            self.stdout.write(self.style.WARNING(f'warning: {warning}'))
        for error in self.errors:
            self.stdout.write(self.style.ERROR(f'error: {error}'))

        if self.errors:
            raise CommandError(
                f'{len(self.errors)} error(s), {len(self.warnings)} warning(s).'
            )
        if self.warnings and options['strict']:
            raise CommandError(f'{len(self.warnings)} warning(s) (--strict).')

        self.stdout.write(self.style.SUCCESS(
            f'Help docs OK: {len(registry.PAGES)} pages, '
            f'{len(screenshots.SHOTS)} screenshots, '
            f'{len(self.warnings)} warning(s).'
        ))

    # -- checks ------------------------------------------------------------

    def _load_permissions(self):
        """Every 'app_label.codename' in the database, or None if unavailable.

        A mistyped permission is silent at runtime — it simply evaluates false
        and the page or section vanishes — so it is worth catching here. Returns
        None on an unmigrated database so the check skips rather than reporting
        every permission as unknown.
        """
        try:
            known = {
                f'{app_label}.{codename}'
                for app_label, codename in Permission.objects.values_list(
                    'content_type__app_label', 'codename',
                )
            }
        except Exception:  # noqa: BLE001 — no database, or not migrated
            known = set()
        if not known:
            self.warnings.append(
                'could not read the permission table, so permission names were '
                'not validated (run migrate first)'
            )
            return None
        return known

    def _check_permission_names(self, label, names, context):
        if self._known_permissions is None:
            return
        for name in names:
            if name not in self._known_permissions:
                self.errors.append(
                    f'{label}: {context} "{name}" is not a real permission — it '
                    f'will always evaluate false and hide the content silently'
                )

    def _check_intros(self):
        for audience in registry.AUDIENCES:
            path = registry.intro_path(audience)
            if not path.exists():
                self.errors.append(
                    f'{audience}: missing index.md (shown at the top of the '
                    f'contents page) — expected at {path}'
                )

    def _check_manifest_matches_disk(self):
        for page in registry.PAGES:
            if not page.path.exists():
                self.errors.append(
                    f'{page.audience}/{page.slug}: listed in registry.PAGES but '
                    f'no file at {page.path}'
                )

        listed = {(p.audience, p.slug) for p in registry.PAGES}
        for audience in registry.AUDIENCES:
            directory = registry.CONTENT_ROOT / audience
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob('*.md')):
                if path.stem == 'index':
                    continue
                if (audience, path.stem) not in listed:
                    self.errors.append(
                        f'{audience}/{path.stem}.md exists but has no entry in '
                        f'registry.PAGES, so nothing links to it'
                    )

    def _check_pages(self):
        known_config = set(rendering.ALL_CONFIG_KEYS)
        specs = screenshots.shot_names()

        for page in registry.PAGES:
            if not page.path.exists():
                continue
            source = page.path.read_text(encoding='utf-8')
            label = f'{page.audience}/{page.slug}'

            if not rendering.TITLE_RE.search(source):
                self.errors.append(
                    f'{label}: no "# " heading — the page title is taken from it'
                )

            for match in rendering.CONFIG_REF_RE.finditer(source):
                key = match.group('key')
                if key not in known_config:
                    self.errors.append(
                        f'{label}: config.{key} is not whitelisted in '
                        f'rendering.CONFIG_KEYS, so it renders as empty'
                    )

            for match in rendering.SCREENSHOT_REF_RE.finditer(source):
                name = match.group('name')
                if name not in specs:
                    self.errors.append(
                        f'{label}: references screenshot "{name}" but there is '
                        f'no matching Shot in helpdocs/screenshots.py'
                    )
                elif rendering.screenshot_url(name) is None:
                    self.warnings.append(
                        f'{label}: screenshot "{name}" has not been captured yet '
                        f'— a placeholder is shown instead'
                    )

            for match in rendering.PAGE_LINK_RE.finditer(source):
                target = match.group('target')
                if rendering.resolve_page_target(target, page.audience) is None:
                    self.errors.append(
                        f'{label}: broken link "help:{target}"'
                    )

            self._check_permission_names(
                label, page.permissions, 'registry permission',
            )
            self._check_permission_names(
                label,
                rendering.permissions_referenced(source),
                'perms. reference',
            )

            try:
                rendered = rendering.render_page(page)
            except Exception as exc:  # noqa: BLE001 — report, don't crash
                self.errors.append(f'{label}: failed to render — {exc!r}')
                continue
            if rendered is None:
                self.errors.append(f'{label}: rendered to nothing')

    def _check_screenshot_specs(self):
        referenced = set()
        for page in registry.PAGES:
            if page.path.exists():
                source = page.path.read_text(encoding='utf-8')
                referenced |= {
                    m.group('name')
                    for m in rendering.SCREENSHOT_REF_RE.finditer(source)
                }

        for shot in screenshots.SHOTS:
            if shot.name not in referenced:
                self.warnings.append(
                    f'screenshot "{shot.name}" is captured but no page uses it'
                )
            if rendering.screenshot_url(shot.name) is None:
                self.warnings.append(
                    f'screenshot "{shot.name}" has no captured PNG — run '
                    f'capture_help_screenshots'
                )

    def _check_admin_coverage(self):
        """Flag admin changelists with no help page.

        A warning, not an error: some admins genuinely don't warrant a page. Add
        deliberate omissions to COVERAGE_EXEMPT with a reason.
        """
        for model in admin.site._registry:
            opts = model._meta
            url_name = f'{opts.app_label}_{opts.model_name}_changelist'
            if url_name in COVERAGE_EXEMPT:
                continue
            if registry.page_for_admin_url_name(url_name) is None:
                self.warnings.append(
                    f'admin "{opts.app_label}.{opts.model_name}" has no help '
                    f'page mapped (add {url_name} to a Page\'s admin_url_names, '
                    f'or to COVERAGE_EXEMPT)'
                )
