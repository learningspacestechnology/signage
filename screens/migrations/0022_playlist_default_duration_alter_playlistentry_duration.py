from django.db import migrations, models


def backfill_default_durations(apps, schema_editor):
    PlaylistEntry = apps.get_model("screens", "PlaylistEntry")
    PlaylistEntry.objects.filter(duration=10).update(duration=None)


class Migration(migrations.Migration):

    dependencies = [
        ("screens", "0021_source_dimensions"),
    ]

    operations = [
        migrations.AddField(
            model_name="playlist",
            name="default_duration",
            field=models.PositiveIntegerField(
                default=10,
                help_text="Default display time in seconds for entries that don't set their own duration (ignored for videos).",
            ),
        ),
        migrations.AlterField(
            model_name="playlistentry",
            name="duration",
            field=models.IntegerField(
                blank=True,
                help_text="seconds to display source for; leave blank to use the playlist's default duration (ignored for videos)",
                null=True,
            ),
        ),
        migrations.RunPython(backfill_default_durations, migrations.RunPython.noop),
    ]
