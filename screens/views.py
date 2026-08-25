from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count
from django.http import HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import render, get_object_or_404
from django.urls import resolve, reverse, Resolver404
from urllib.parse import urlparse
from screens import models
from screens.team_scope import scope_to_active_team, scope_to_user_teams
from screens.utils import get_client_ip, get_client_hostname
from django.utils import timezone
from advertising.settings import AUTO_MAKE_SCREENS_FOR_NEW_IPS, UNCONFIGURED_SCREEN_MESSAGE


_TICKER_SENTINEL_PLAYLIST_ID = -1
_TICKER_SENTINEL_LAST_UPDATED = "1970-01-01T00:00:00"

# The player reads `interspersed.playlist.items.length` with no optional
# chaining, so each key must be either null or an object that always carries an
# items array. Emitting `{}` throws during render and the screen goes black.
NO_INTERSPERSED = {"playlist": None, "screen": None}


def _ticker_redirect_payload(screen):
    """Single-iframe playlist that points the outer Vue at the wrapper template."""
    wrapper_url = reverse("screens/screen_wrapper", args=[screen.id])
    return {
        "playlist": [{"src": wrapper_url, "type": models.Source.IFRAME, "duration": 86400}],
        "interspersed": dict(NO_INTERSPERSED),
        "current_playlist": _TICKER_SENTINEL_PLAYLIST_ID,
        "playlist_last_updated": _TICKER_SENTINEL_LAST_UPDATED,
        "screen_id": screen.id,
    }


def get_screen(request):
    try:
        referer_match = resolve(urlparse(request.META.get("HTTP_REFERER", "http://example.com/"))[2])
    except Resolver404 as e:
        referer_match = None
    if referer_match and referer_match.url_name == "screens/screen_view":
        return get_object_or_404(models.Screen, id=referer_match.kwargs["screen_id"])

    # screen is from the auto url
    ip = get_client_ip(request)
    screen = models.Screen.objects.filter(ip=ip).first()
    if screen:
        return screen

    if AUTO_MAKE_SCREENS_FOR_NEW_IPS:
        return models.Screen.objects.create(
            ip=ip,
            name=get_client_hostname(ip),
            schedule=models.Schedule.get_default(),
        )

    return None


def view_unconfigured(request):
    ip = get_client_ip(request)
    return render(request, 'screens/unconfigured_screen.html', {
        'ip': ip,
        'hostname': get_client_hostname(ip),
        'message': UNCONFIGURED_SCREEN_MESSAGE,
    }, status=404)


_UNCONFIGURED_PAYLOAD = {
    "playlist": [{"src": "/api/unconfigured", "type": models.Source.IFRAME, "duration": 3600}],
    "interspersed": dict(NO_INTERSPERSED),
    "current_playlist": -1,
    "playlist_last_updated": "1970-01-01T00:00:00",
    "screen_id": None,
}

_UNCONFIGURED_META = {
    "current_playlist": -1,
    "playlist_last_updated": "1970-01-01T00:00:00",
}


def _unconfigured_json(request):
    return JsonResponse(_UNCONFIGURED_PAYLOAD)


def view_screen_automatic(request):
    screen = get_screen(request)
    if screen is None:
        return view_unconfigured(request)
    return view_screen(request, screen.id)


def view_screen(request, screen_id):
    """Dev-only renderer. In production nginx serves the Vue player for
    /screen/<id>; this view is only reached under runserver. It plays the base
    playlist without interspersion — the interleaving lives in the player."""
    try:
        screen = models.Screen.objects.get(id=screen_id)
        if screen.schedule:
            current_playlist = screen.schedule.get_playlist()
            view_dict = {
                'playlist': current_playlist.get_resolved_sources(),
                "current_playlist": current_playlist.pk,
                "playlist_last_updated": current_playlist.last_updated.isoformat(),
                "screen_id": screen_id,
            }
            return render(request, 'screens/basic_screen.html', view_dict)
        else:
            return HttpResponse ("<meta http-equiv='refresh' content='60'/>No playlist set for this screen")
    except models.Screen.DoesNotExist:
        return HttpResponse("Requested screen not found")


def view_playlist(request, playlist_id):
    """Dev-only renderer — see view_screen."""
    try:
        current_playlist = models.Playlist.objects.get(id=playlist_id)
        view_dict = {
            'playlist': current_playlist.get_resolved_sources(),
            "current_playlist": current_playlist.pk,
            "playlist_last_updated": current_playlist.last_updated.isoformat()
        }
        return render(request, 'screens/basic_screen.html', view_dict)
    except models.Playlist.DoesNotExist:
        return HttpResponse("Requested playlist not found")


def view_screen_automatic_json(request):
    screen = get_screen(request)
    if screen is None:
        return _unconfigured_json(request)
    return view_screen_json(request, screen.id)


def view_screen_json(request, screen_id):
    try:
        screen = models.Screen.objects.get(id=screen_id)
    except models.Screen.DoesNotExist:
        return JsonResponse({"error": "screen doesnt exist"}, status=404)
    if not screen.schedule:
        return _unconfigured_json(request)
    if screen.has_ticker():
        return JsonResponse(_ticker_redirect_payload(screen))
    current_playlist = screen.schedule.get_playlist()
    return JsonResponse(render_playlist_json(
        current_playlist,
        screen=screen,
        screen_id=screen_id,
    ))


def view_screen_wrapper(request, screen_id):
    screen = get_object_or_404(models.Screen, id=screen_id)
    if not screen.has_ticker():
        # Ticker was disabled between page load and now; bounce to plain screen URL.
        return HttpResponseRedirect(reverse("screens/screen_view", args=[screen_id]))
    if not screen.schedule:
        return HttpResponse("No playlist set for this screen")
    current_playlist = screen.schedule.get_playlist()
    return render(request, "screens/screen_with_ticker.html", {
        "screen": screen,
        "style": screen.resolved_ticker_style(),
        "current_playlist_id": current_playlist.pk,
    })


def view_playlist_json(request, playlist_id):
    try:
        current_playlist = models.Playlist.objects.get(id=playlist_id)
        return JsonResponse(render_playlist_json(current_playlist))
    except models.Playlist.DoesNotExist:
        return JsonResponse({"error": "playlist doesnt exist"}, status=404)


def serialize_entries(entries):
    return [{"src": e.source.src(), "type": e.source.type, "duration": e.duration} for e in entries]


def _interspersed_stream(playlist, rate):
    """One interspersed stream, or None when there is nothing to intersperse.

    Returning None rather than an empty object is load-bearing: the player
    dereferences `.items` without guarding, so a stream key must never be an
    object lacking it.
    """
    if not playlist:
        return None
    items = serialize_entries(playlist.get_interspersed_sources())
    if not items:
        return None
    # The player clamps identically; keep the two in step.
    return {"items": items, "rate": max(1, rate or 1)}


def aggregate_last_updated(playlist, screen=None):
    """Newest publish time across everything that feeds this screen's content.

    The interspersed playlists are separate rows, so their edits do not touch
    the base playlist's own last_updated; without folding them in here, changing
    a logo playlist would never reach any device.
    """
    candidates = [playlist.last_updated]
    if playlist.interspersed_playlist:
        candidates.append(playlist.interspersed_playlist.last_updated)
    if screen:
        candidates.append(screen.last_updated)
        if screen.interspersed_playlist:
            candidates.append(screen.interspersed_playlist.last_updated)
    return max(candidates)


def render_last_updated(playlist, screen=None):
    """The single source of the publish timestamp.

    /api/screen/<id> and /api/meta must render byte-identical strings, or the
    player's strict !== diff never settles and it refetches on every poll. That
    is the whole reason this is a function rather than an expression repeated at
    each call site.

    Rendered in local civil time, so the offset matches what the admin displays
    and what anyone reading /api/meta by hand expects. The player only compares
    two strings that both come from here, so the zone is cosmetic to it -- but
    both endpoints must pick the same one, which is again why this is a funnel.
    """
    return timezone.localtime(aggregate_last_updated(playlist, screen)).isoformat()


def render_playlist_json(playlist, screen=None, screen_id=None):
    interspersed = {
        "playlist": _interspersed_stream(
            playlist.interspersed_playlist, playlist.interspersed_rate),
        "screen": _interspersed_stream(
            screen.interspersed_playlist, screen.interspersed_rate) if screen else None,
    }
    # The single-item hold stops a lone image being replaced by itself. With an
    # interspersed stream it is alternating with something, so the hold would
    # only mean an hour of that one item between each logo.
    hold_single = not (interspersed["playlist"] or interspersed["screen"])

    return {
        'playlist': serialize_entries(playlist.get_resolved_sources(hold_single=hold_single)),
        'interspersed': interspersed,
        "current_playlist": playlist.pk,
        "playlist_last_updated": render_last_updated(playlist, screen),
        "screen_id": screen_id
    }


@staff_member_required
def view_playlist_tree_json(request):
    """The inheritance graph, scoped to what the viewer's active team may see.

    Visible = the active team's own playlists, plus everything connected to them
    by inheritance: the chain they inherit content *from*, and the chain that
    inherits *from* them. Both directions may cross into another team — you need
    to see where your content comes from and where it ends up. Playlists with no
    inheritance path to the active team's own never appear.
    """
    base = models.Playlist.objects.all()
    # ActiveTeamMiddleware resolves active_team for this endpoint; the fallback
    # keeps a missing one narrow rather than widening to every playlist.
    if getattr(request, "active_team", None) is not None:
        accessible = scope_to_active_team(base, request)
    else:
        accessible = scope_to_user_teams(base, request)
    accessible_ids = set(accessible.values_list("id", flat=True))

    visible_ids = set(accessible_ids)

    frontier = set(accessible_ids)
    while frontier:
        parents = set(
            models.PlaylistRelation.objects
                .filter(inheriting_list_id__in=frontier)
                .values_list("super_list_id", flat=True)
        ) - visible_ids
        if not parents:
            break
        visible_ids |= parents
        frontier = parents

    frontier = set(accessible_ids)
    while frontier:
        children = set(
            models.PlaylistRelation.objects
                .filter(super_list_id__in=frontier)
                .values_list("inheriting_list_id", flat=True)
        ) - visible_ids
        if not children:
            break
        visible_ids |= children
        frontier = children

    playlists = (
        models.Playlist.objects
        .filter(id__in=visible_ids)
        .prefetch_related("children_list")
        .annotate(source_count=Count("playlistentry"))
    )
    out = {}
    for pl in playlists:
        out[pl.id] = {
            "name": pl.name,
            "description": pl.description,
            "source_count": pl.source_count,
            "children": [
                child_id for child_id in pl.children_list.values_list("inheriting_list_id", flat=True)
                if child_id in visible_ids
            ],
        }
    return JsonResponse(out)


def _get_meta(request, screen):
    if screen.schedule is None:
        return JsonResponse(_UNCONFIGURED_META)

    playlist = screen.schedule.get_playlist()
    # save(update_fields=[...]) rather than a plain save(): Model._save_table
    # filters the field list by update_fields *before* calling field.pre_save(),
    # so Screen.last_updated's auto_now never fires. This is the 60-second
    # heartbeat -- stamping it would move the published timestamp every minute,
    # the player's :key would change, it would remount the Playlist component,
    # and every screen in the estate would restart from item one once a minute.
    #
    # Only last_seen is in the UPDATE, so an admin edit made in the intervening
    # seconds is not written back over. Two differences from the queryset
    # .update() this replaced, both accepted: pre_save/post_save now fire on
    # Screen (no receivers today; any added later runs once per device per
    # minute), and Django raises DatabaseError if the row was deleted between
    # the read and this write, where .update() silently affected zero rows.
    screen.last_seen = timezone.now()
    screen.save(update_fields=["last_seen"])

    if screen.has_ticker():
        # Match the sentinel returned by /api/screen so outer Vue's diff stays quiet
        # while the wrapper is in charge. Real text/playlist live in extra fields.
        return JsonResponse({
            "current_playlist": _TICKER_SENTINEL_PLAYLIST_ID,
            "playlist_last_updated": _TICKER_SENTINEL_LAST_UPDATED,
            "ticker_enabled": True,
            "ticker_text": screen.ticker_text,
            "ticker_current_playlist": playlist.pk,
        })

    return JsonResponse({
        "current_playlist": playlist.pk,
        "playlist_last_updated": render_last_updated(playlist, screen),
        "ticker_enabled": False,
        "ticker_text": "",
    })


def get_meta(request):
    screen = get_screen(request)
    if screen is None:
        return JsonResponse(_UNCONFIGURED_META)
    return _get_meta(request, screen)


def get_meta_screen(request, screen_id):
    screen = models.Screen.objects.get(id=screen_id)
    return _get_meta(request, screen)
