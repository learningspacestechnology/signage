"""Helpers for scoping querysets to a request's team context."""

from advertising.middleware import ALL_TEAMS


def scope_to_active_team(qs, request):
    """Filter qs to objects owned by the active team (or unfiltered for ALL_TEAMS)."""
    active = getattr(request, 'active_team', None)
    if active is None or active is ALL_TEAMS:
        return qs.distinct()
    return qs.filter(teams=active).distinct()


def scope_to_user_teams(qs, request):
    """Filter qs to objects owned by any team the request user belongs to.

    Superusers see everything. Used for cross-team picker widgets such as
    PlaylistRelation.super_list and PlaylistEntry.source, where the rule is
    'pick from any of your teams' rather than 'pick from the active team'.
    """
    if request.user.is_superuser:
        return qs.distinct()
    return qs.filter(teams__in=request.user.teams.all()).distinct()
