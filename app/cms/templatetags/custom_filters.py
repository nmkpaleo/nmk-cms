from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key, None)


@register.simple_tag(takes_context=True)
def querystring_replace(context, **kwargs):
    """Return the current querystring updated with the provided parameters."""
    request = context.get("request")
    if request is None:
        return ""

    query = request.GET.copy()
    for key, value in kwargs.items():
        if value in (None, ""):
            query.pop(key, None)
        else:
            query[key] = value
    return query.urlencode()


@register.simple_tag
def page_range(page_obj):
    """Return a compact, elided page range for a paginated page object."""
    return page_obj.paginator.get_elided_page_range(
        number=page_obj.number,
        on_each_side=2,
        on_ends=1,
    )
