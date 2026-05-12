from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("screens", "0022_playlist_default_duration_alter_playlistentry_duration"),
    ]

    operations = [
        migrations.AlterField(
            model_name="playlist",
            name="description",
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name="schedule",
            name="description",
            field=models.TextField(blank=True),
        ),
    ]
