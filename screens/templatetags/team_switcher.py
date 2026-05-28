from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def team_switcher_items(context):
    from advertising.admin import team_switcher_dropdown

    request = context.get("request")
    if request is None:
        return []
    return team_switcher_dropdown(request)
