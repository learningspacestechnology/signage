"""Turn a help markdown file into HTML.

The pipeline, in order:

1. **Config substitution.** The markdown *source* is run through the Django
   template engine with a single whitelisted ``config`` dict. Pages write
   ``{{ config.MAX_IMG_WIDTH }}`` rather than a literal number, because those
   values genuinely differ between deployments — ``ADMIN_SITE_NAME`` and
   ``MAX_IMG_*`` are already overridden in dev. `check_help_docs` rejects any
   key that isn't whitelisted, so a typo can't silently render as empty.
   (Consequence for authors: a page that needs to *show* Django template syntax
   must wrap it in ``{% verbatim %}``.)
2. **Screenshot references.** ``![Alt](screenshot:name)`` resolves to the
   collected static file. When the PNG hasn't been captured yet a labelled
   placeholder is rendered instead, so pages stay readable before — or without —
   a screenshot run.
3. **Page references.** ``[text](help:slug)`` links to another page in the same
   audience; ``[text](help:technical/slug)`` crosses audiences. Plain relative
   paths would be wrong here — page URLs end in a slash, so ``](dashboard)``
   would resolve *below* the current page rather than beside it.
4. **Markdown → HTML**, then standalone images are wrapped in ``<figure>`` so
   their alt text can double as a caption.

Results are cached against the file's mtime: edits show up immediately in dev,
and each file is converted once per process in production.
"""
import hashlib
import re

from django.conf import settings
from django.contrib.auth.context_processors import PermWrapper
from django.contrib.staticfiles import finders
from django.core.cache import cache
from django.template import Context, Template
from django.templatetags.static import static
from django.utils.html import escape

import markdown
from markdown.extensions.toc import TocExtension

from helpdocs import registry

#: Settings a page may reference as ``{{ config.NAME }}``. Deliberately a
#: whitelist: help pages should not be able to print SECRET_KEY.
CONFIG_KEYS = (
    'ADMIN_SITE_NAME',
    'MAX_IMG_WIDTH',
    'MAX_IMG_HEIGHT',
    'UNCONFIGURED_SCREEN_MESSAGE',
    'IP_ACCESS_CONTROL_ENABLED',
    'ENTRA_AUTH_ENABLED',
    'AUTO_MAKE_SCREENS_FOR_NEW_IPS',
    'TIME_ZONE',
)

#: Derived values that aren't settings in their own right but would otherwise be
#: hardcoded in prose. Computed by ``_derived_config()``.
DERIVED_CONFIG_KEYS = (
    'CONTENT_TASK_MINUTES',
    'ROOM_EVENT_SCHEDULE',
    'ROOM_CLEANUP_SCHEDULE',
    'ROOM_SYNC_SCHEDULE',
    'SCREEN_OFFLINE_AFTER',
)

ALL_CONFIG_KEYS = CONFIG_KEYS + DERIVED_CONFIG_KEYS

#: ``![Alt text](screenshot:some-name)``
SCREENSHOT_IMAGE_RE = re.compile(
    r'!\[(?P<alt>[^\]]*)\]\(screenshot:(?P<name>[a-z0-9][a-z0-9\-]*)\)'
)

#: Used by check_help_docs to find every reference, including malformed ones.
SCREENSHOT_REF_RE = re.compile(r'\(screenshot:(?P<name>[^)]*)\)')

#: ``[text](help:slug)`` or ``[text](help:audience/slug)``
PAGE_LINK_RE = re.compile(r'\]\(help:(?P<target>[^)\s]+)\)')

#: Any ``config.SOMETHING`` reference — used by check_help_docs. Deliberately
#: broad so it also catches ``{% if config.X %}``, not just ``{{ config.X }}``.
CONFIG_REF_RE = re.compile(r'\bconfig\.(?P<key>\w+)')

#: ``perms.app_label.codename`` — a page gating a section on a permission.
PERMS_REF_RE = re.compile(r'\bperms\.(?P<app>\w+)\.(?P<codename>\w+)')

TITLE_RE = re.compile(r'^#\s+(?P<title>.+?)\s*$', re.MULTILINE)

#: A paragraph containing nothing but one image.
LONE_IMAGE_P_RE = re.compile(
    r'<p>(?P<img><img\b[^>]*/?>)</p>', re.IGNORECASE
)
IMG_ALT_RE = re.compile(r'\balt="(?P<alt>[^"]*)"', re.IGNORECASE)

SCREENSHOT_STATIC_PREFIX = 'helpdocs/screenshots/'


def _describe_schedule(schedule):
    """Human wording for a CELERY_BEAT_SCHEDULE entry's `schedule` value."""
    if isinstance(schedule, (int, float)):
        minutes = int(schedule) // 60
        if minutes >= 1:
            return f'every {minutes} minute{"s" if minutes != 1 else ""}'
        return f'every {int(schedule)} seconds'

    # celery.schedules.crontab
    hour = getattr(schedule, 'hour', None)
    minute = getattr(schedule, 'minute', None)
    try:
        minute_val = min(minute)
        hours = sorted(hour)
    except TypeError:
        return str(schedule)

    if len(hours) == 24:
        return f'every hour, at {minute_val:02d} minutes past'
    if len(hours) == 1:
        return f'daily at {hours[0]:02d}:{minute_val:02d}'
    return str(schedule)


def _schedule_for_task(task_name, default=''):
    for entry in getattr(settings, 'CELERY_BEAT_SCHEDULE', {}).values():
        if entry.get('task') == task_name:
            return _describe_schedule(entry.get('schedule'))
    return default


def _derived_config():
    return {
        'CONTENT_TASK_MINUTES': _schedule_for_task(
            'screens.tasks.cleanup_sources', 'every 5 minutes'),
        'ROOM_EVENT_SCHEDULE': _schedule_for_task(
            'room_schedules.tasks.build_schedule', 'every hour'),
        'ROOM_CLEANUP_SCHEDULE': _schedule_for_task(
            'room_schedules.tasks.cleanup_schedule', 'daily at midnight'),
        'ROOM_SYNC_SCHEDULE': _schedule_for_task(
            'room_schedules.tasks.sync_o365_rooms', 'daily at 02:15'),
        # Screen.online() compares last_seen against now - 1 minute.
        'SCREEN_OFFLINE_AFTER': 'one minute',
    }


def config_context():
    values = {key: getattr(settings, key, '') for key in CONFIG_KEYS}
    values.update(_derived_config())
    return values


class _AllPermissions:
    """Stand-in for ``perms`` that grants everything.

    Used when rendering without a user — ``check_help_docs`` and the registry
    tests need to see a page in full, not the subset some hypothetical reader
    would get.
    """

    def __getitem__(self, _key):
        return self

    def __contains__(self, _item):
        return True

    def __bool__(self):
        return True


def permissions_referenced(source):
    """The 'app.codename' permissions a page's own markup gates sections on."""
    return sorted({
        f"{m.group('app')}.{m.group('codename')}"
        for m in PERMS_REF_RE.finditer(source)
    })


def _perms_context(user):
    return _AllPermissions() if user is None else PermWrapper(user)


def _permission_fingerprint(source, user):
    """Cache-key component covering the permissions this page branches on.

    Rendered output depends on the reader once a page gates a section, so the
    cache must not be shared across users. Keying on only the permissions the
    page actually references keeps that to a handful of variants rather than one
    entry per user.
    """
    referenced = permissions_referenced(source)
    if not referenced:
        return 'all'
    if user is None:
        return 'unrestricted'
    granted = ''.join('1' if user.has_perm(p) else '0' for p in referenced)
    digest = hashlib.sha1(
        ('|'.join(referenced) + ':' + granted).encode('utf-8')
    ).hexdigest()
    return digest[:12]


def screenshot_url(name):
    """Static URL for a captured screenshot, or None if it isn't there yet."""
    relative = f'{SCREENSHOT_STATIC_PREFIX}{name}.png'
    if finders.find(relative) is None:
        return None
    return static(relative)


def _placeholder_html(name, alt):
    label = escape(alt or name)
    return (
        '<div class="help-screenshot-missing" role="note">'
        f'<strong>Screenshot pending:</strong> {label} '
        f'<code>({escape(name)})</code>'
        '</div>'
    )


def _expand_screenshot_refs(source):
    def replace(match):
        name = match.group('name')
        alt = match.group('alt')
        url = screenshot_url(name)
        if url is None:
            # Raw HTML block — markdown passes it through untouched.
            return f'\n\n{_placeholder_html(name, alt)}\n\n'
        return f'![{alt}]({url})'

    return SCREENSHOT_IMAGE_RE.sub(replace, source)


def resolve_page_target(target, current_audience):
    """``'slug'`` or ``'audience/slug'`` → a registry Page, or None if unknown."""
    if '/' in target:
        audience, _, slug = target.partition('/')
    else:
        audience, slug = current_audience, target
    if audience not in registry.AUDIENCES:
        return None
    return registry.get_page(audience, slug)


def _expand_page_refs(source, current_audience):
    def replace(match):
        target = match.group('target')
        page = resolve_page_target(target, current_audience)
        if page is None:
            # Leave the literal so the break is visible on the page rather than
            # silently linking somewhere wrong. check_help_docs reports it.
            return match.group(0)
        return f']({page.url})'

    return PAGE_LINK_RE.sub(replace, source)


def _wrap_figures(html):
    """Give standalone images a <figure>/<figcaption> using their alt text."""
    def replace(match):
        img = match.group('img')
        alt_match = IMG_ALT_RE.search(img)
        alt = alt_match.group('alt') if alt_match else ''
        caption = f'<figcaption>{alt}</figcaption>' if alt.strip() else ''
        return f'<figure class="help-figure">{img}{caption}</figure>'

    return LONE_IMAGE_P_RE.sub(replace, html)


def _make_converter():
    return markdown.Markdown(
        extensions=[
            'extra',            # tables, fenced_code, attr_list, def_list, ...
            'admonition',
            'sane_lists',
            'smarty',
            TocExtension(permalink=False, toc_depth='2-3', anchorlink=True),
        ],
        output_format='html5',
    )


def render_source(source, audience=registry.USERS, user=None):
    """Markdown string → {'html': ..., 'toc': ..., 'title': ...}.

    `user` is only needed by pages that gate a section on ``perms.*``; pass None
    to render everything.
    """
    title_match = TITLE_RE.search(source)
    title = title_match.group('title') if title_match else ''

    rendered = Template(source).render(
        Context(
            {'config': config_context(), 'perms': _perms_context(user)},
            autoescape=False,
        )
    )
    rendered = _expand_screenshot_refs(rendered)
    rendered = _expand_page_refs(rendered, audience)

    converter = _make_converter()
    html = converter.convert(rendered)
    html = _wrap_figures(html)

    return {
        'html': html,
        'toc': getattr(converter, 'toc', ''),
        'title': title,
    }


def _render_file(path, audience, cache_prefix, user=None):
    """Render a markdown file, cached against its mtime and the reader's perms.

    Keying on mtime means an edit is picked up on the next request in
    development, while production converts each file only once per process. The
    permission fingerprint keeps a page that hides a section from leaking the
    hidden version to someone who should see it, or vice versa.
    """
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        return None

    source = path.read_text(encoding='utf-8')
    fingerprint = _permission_fingerprint(source, user)
    key = f'helpdocs:{cache_prefix}:{path}:{mtime}:{fingerprint}'
    result = cache.get(key)
    if result is None:
        result = render_source(source, audience, user)
        cache.set(key, result, None)
    return result


def render_page(page, user=None):
    """Render a registry Page. Returns None when its file is missing."""
    return _render_file(page.path, page.audience, 'page', user)


def render_intro(audience, user=None):
    """Render an audience's index.md. Returns None when absent."""
    return _render_file(registry.intro_path(audience), audience, 'intro', user)


def page_title(page):
    """The page's `# ` heading, falling back to a slug-derived title.

    Read straight off the file rather than from a render: the title is never
    inside a permission-gated section, and the index needs a title per page —
    rendering each one just to read its heading would be wasteful and would make
    titles depend on the reader.
    """
    try:
        mtime = page.path.stat().st_mtime_ns
    except OSError:
        return page.slug.replace('-', ' ').capitalize()

    key = f'helpdocs:title:{page.path}:{mtime}'
    title = cache.get(key)
    if title is None:
        match = TITLE_RE.search(page.path.read_text(encoding='utf-8'))
        title = match.group('title') if match else ''
        cache.set(key, title, None)
    return title or page.slug.replace('-', ' ').capitalize()
