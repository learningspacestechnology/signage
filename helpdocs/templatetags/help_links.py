"""Template helpers for the help documentation."""
from django import template
from unfold.widgets import PROSE_CLASSES

from helpdocs import registry

register = template.Library()


@register.simple_tag
def prose_classes():
    """Unfold's own prose utility list, so rendered markdown matches the admin.

    Unfold ships a pre-compiled Tailwind build and there is no build step in this
    project, so we reuse the exact class list Unfold uses for its own rich-text
    output rather than inventing one. Light/dark handling comes for free.
    """
    return ' '.join(PROSE_CLASSES)


@register.inclusion_tag('admin/helpdocs/_help_hint.html', takes_context=True)
def help_hint(context):
    """Render a link to the help page for the admin view being displayed.

    Injected above changelists and change forms via ``HelpLinkAdminMixin``.
    Renders nothing when the current view has no mapped page, or when the reader
    lacks permission for that page's audience — so it never offers a link that
    would 403.
    """
    request = context.get('request')
    if request is None:
        return {'page': None}

    match = getattr(request, 'resolver_match', None)
    page = registry.page_for_admin_url_name(
        getattr(match, 'url_name', None) if match else None
    )
    # can_read_page covers the audience gate and the page's own permissions, so
    # the hint never offers a link that would answer with a 403.
    if page is None or not registry.can_read_page(request.user, page):
        return {'page': None}

    # Imported lazily: rendering pulls in the markdown converter, which is not
    # needed on admin pages that have no mapped help page.
    from helpdocs import rendering

    return {
        'page': page,
        'title': rendering.page_title(page),
        'summary': page.summary,
        'url': page.url,
    }
