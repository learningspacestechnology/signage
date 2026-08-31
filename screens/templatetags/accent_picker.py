from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def accent_picker_items(context):
    from advertising.admin import accent_picker_items as build_items

    request = context.get("request")
    if request is None:
        return []
    return build_items(request)
