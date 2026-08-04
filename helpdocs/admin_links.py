"""Attach contextual help links to the admin.

django-unfold's ``ModelAdmin`` exposes ``list_before_template`` and
``change_form_before_template`` injection slots, so a help link can be added
without shadowing or overriding any admin template.

Rather than mixing a class into every ``ModelAdmin`` — which for
``room_schedules`` would mean editing a git submodule — this walks the registry
once and points each *mapped* admin at the slot template. Which admins are mapped
is decided by ``admin_url_names`` in ``helpdocs/registry.py``, so adding a
mapping there is all it takes for the link to appear.
"""
from django.contrib import admin

from helpdocs import registry

HELP_HINT_SLOT = 'admin/helpdocs/_help_hint_slot.html'


def attach_help_links(site=None):
    """Wire the help-hint slot into every ModelAdmin that has a mapped page.

    Call this *after* all admin modules have loaded and any re-registration has
    happened, otherwise a later ``unregister``/``register`` pair silently drops
    the attachment. ``advertising/admin.py`` calls it as its last statement.

    An admin that already sets one of these slots for its own purposes is left
    alone.
    """
    site = site or admin.site
    mapped = set(registry.ADMIN_URL_INDEX)

    # ``_registry`` is the only way to enumerate admins without a request;
    # ``get_app_list`` needs one and filters by permission.
    for model, model_admin in site._registry.items():
        opts = model._meta
        prefix = f'{opts.app_label}_{opts.model_name}_'

        if f'{prefix}changelist' in mapped:
            if not getattr(model_admin, 'list_before_template', None):
                model_admin.list_before_template = HELP_HINT_SLOT

        if {f'{prefix}change', f'{prefix}add'} & mapped:
            if not getattr(model_admin, 'change_form_before_template', None):
                model_admin.change_form_before_template = HELP_HINT_SLOT
