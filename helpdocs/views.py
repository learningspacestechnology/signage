"""Help documentation pages, served inside the admin.

Follows the project's existing pattern for a custom admin page: a plain function
view returning a ``TemplateResponse`` built on ``admin.site.each_context`` — the
same shape as ``playlist_tree_view`` in ``screens/admin.py`` and the O365 views in
``room_schedules/admin.py``.
"""
import json

from django.contrib import admin
from django.http import Http404
from django.template.response import TemplateResponse
from django.urls import reverse

from helpdocs import registry, rendering


def can_read(user, audience):
    """Whether `user` may read `audience`. Also used by the sidebar and template tag."""
    return registry.can_read_audience(user, audience)


def _audience_tabs(request, current):
    tabs = []
    for audience in registry.AUDIENCES:
        if not can_read(request.user, audience):
            continue
        tabs.append({
            'key': audience,
            'label': registry.AUDIENCE_LABELS[audience],
            'icon': registry.AUDIENCE_ICONS[audience],
            'url': _audience_url(audience),
            'is_current': audience == current,
        })
    return tabs


def _audience_url(audience):
    return reverse('admin:help_section', kwargs={'audience': audience})


def _entries_for(audience, user):
    """Sections with their visible pages, titles resolved, search text built.

    Pages the reader lacks permission for are dropped here, and a section left
    with nothing in it disappears entirely. ``search`` is what the index page's
    client-side filter matches against, so it is built here rather than
    assembled in JavaScript.
    """
    sections = []
    for section, pages in registry.sections_for(audience, user):
        entries = []
        for page in pages:
            title = rendering.page_title(page)
            entries.append({
                'page': page,
                'slug': page.slug,
                'title': title,
                'summary': page.summary,
                'url': page.url,
                'search': f'{title} {page.summary} {section}'.lower(),
            })
        sections.append({
            'title': section,
            'entries': entries,
            'search': ' '.join(e['search'] for e in entries),
        })
    return sections


def _flat_pages(audience, user):
    return [p for _, pages in registry.sections_for(audience, user) for p in pages]


def _neighbours(page, user):
    """Previous/next within the pages this reader can actually open."""
    ordered = _flat_pages(page.audience, user)
    try:
        index = ordered.index(page)
    except ValueError:
        return None, None
    previous = ordered[index - 1] if index > 0 else None
    following = ordered[index + 1] if index < len(ordered) - 1 else None
    return previous, following


def _as_link(page):
    if page is None:
        return None
    return {'title': rendering.page_title(page), 'url': page.url}


def _related_admin_link(request, page):
    """"Open this screen" link for the first changelist the page documents.

    Resolved via ``get_app_list``, which already filters by view permission and
    hands back the URL — so the link never appears for someone who would only get
    a 403 by following it, and app labels containing underscores work without
    string surgery.
    """
    wanted = {n for n in page.admin_url_names if n.endswith('_changelist')}
    if not wanted:
        return None

    for app in admin.site.get_app_list(request):
        for model in app['models']:
            url_name = (
                f"{app['app_label']}_{model['object_name'].lower()}_changelist"
            )
            if url_name in wanted and model.get('admin_url'):
                return {
                    'label': f"Open {model['name']}",
                    'url': model['admin_url'],
                }
    return None


def _forbidden(request, audience, page=None):
    """The reader may not open this audience, or this particular page."""
    context = admin.site.each_context(request)
    context.update({
        'title': 'Documentation not available',
        'audience_label': registry.AUDIENCE_LABELS.get(audience, audience),
        'help_index_url': _audience_url(registry.USERS),
        # A page-level refusal is about the feature, not the doc set — say so,
        # otherwise "ask for documentation access" is misleading advice.
        'is_page_level': page is not None,
    })
    return TemplateResponse(
        request, 'admin/helpdocs/forbidden.html', context, status=403,
    )


def help_index(request, audience=None):
    """Contents page for an audience. `/admin/help/` lands on the user set."""
    if audience is None:
        audience = registry.USERS
    if audience not in registry.AUDIENCES:
        raise Http404('Unknown documentation audience')
    if not can_read(request.user, audience):
        return _forbidden(request, audience)

    intro = rendering.render_intro(audience, request.user)
    sections = _entries_for(audience, request.user)

    context = admin.site.each_context(request)
    context.update({
        'title': registry.AUDIENCE_LABELS[audience],
        'audience': audience,
        'audience_label': registry.AUDIENCE_LABELS[audience],
        'audience_tabs': _audience_tabs(request, audience),
        'intro_html': intro['html'] if intro else '',
        'sections': sections,
        # Search blobs for the client-side filter, so it counts matches without
        # walking the DOM.
        'search_items_json': json.dumps(
            [e['search'] for s in sections for e in s['entries']]
        ),
    })
    return TemplateResponse(request, 'admin/helpdocs/index.html', context)


def help_page(request, audience, slug):
    """A single rendered documentation page."""
    if audience not in registry.AUDIENCES:
        raise Http404('Unknown documentation audience')

    page = registry.get_page(audience, slug)
    if page is None:
        raise Http404('No such help page')

    if not can_read(request.user, audience):
        return _forbidden(request, audience)
    if not registry.can_read_page(request.user, page):
        return _forbidden(request, audience, page=page)

    rendered = rendering.render_page(page, request.user)
    if rendered is None:
        # Listed in the manifest but the file is missing — a broken link is worse
        # than a 404, and check_help_docs reports this as an error.
        raise Http404('Help page content is missing')

    previous, following = _neighbours(page, request.user)

    context = admin.site.each_context(request)
    context.update({
        'title': rendered['title'] or page.slug,
        'audience': audience,
        'audience_label': registry.AUDIENCE_LABELS[audience],
        'audience_tabs': _audience_tabs(request, audience),
        'audience_url': _audience_url(audience),
        'page': page,
        'page_html': rendered['html'],
        'page_toc': rendered['toc'],
        'section': page.section,
        'summary': page.summary,
        'previous_page': _as_link(previous),
        'next_page': _as_link(following),
        'related_admin_link': _related_admin_link(request, page),
    })
    return TemplateResponse(request, 'admin/helpdocs/page.html', context)
