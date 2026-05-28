from django.db import migrations

DEFAULT_TEAM_NAME = "Default"


def forwards(apps, schema_editor):
    Team = apps.get_model("screens", "Team")
    TeamMembership = apps.get_model("screens", "TeamMembership")
    Source = apps.get_model("screens", "Source")
    Playlist = apps.get_model("screens", "Playlist")
    Screen = apps.get_model("screens", "Screen")
    Schedule = apps.get_model("screens", "Schedule")
    User = apps.get_model("auth", "User")

    team, _ = Team.objects.get_or_create(name=DEFAULT_TEAM_NAME)

    for user in User.objects.all():
        TeamMembership.objects.get_or_create(user=user, team=team)

    for model in (Source, Playlist, Screen, Schedule):
        for obj in model.objects.all():
            obj.teams.add(team)


def backwards(apps, schema_editor):
    Team = apps.get_model("screens", "Team")
    TeamMembership = apps.get_model("screens", "TeamMembership")
    Source = apps.get_model("screens", "Source")
    Playlist = apps.get_model("screens", "Playlist")
    Screen = apps.get_model("screens", "Screen")
    Schedule = apps.get_model("screens", "Schedule")

    try:
        team = Team.objects.get(name=DEFAULT_TEAM_NAME)
    except Team.DoesNotExist:
        return

    for model in (Source, Playlist, Screen, Schedule):
        for obj in model.objects.filter(teams=team):
            obj.teams.remove(team)

    TeamMembership.objects.filter(team=team).delete()
    team.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("screens", "0025_team_models"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
