"""Models and migration files agree, so `makemigrations --check` is a usable gate."""

from django.apps import apps
from django.conf import settings
from django.db.migrations.autodetector import MigrationAutodetector
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.questioner import NonInteractiveMigrationQuestioner
from django.db.migrations.state import ProjectState
from django.forms.models import modelform_factory
from django.test import SimpleTestCase, override_settings

from screens.forms import PlaylistAssigningSourceForm, SourceBulkCreateForm
from screens.models import Source
from screens.models.source import file_help_text


class NoPendingMigrationsTests(SimpleTestCase):
    """`makemigrations --check` reported a permanent phantom until MAX_IMG_WIDTH and
    MAX_IMG_HEIGHT left `Source.file`'s help_text.

    Django records the whole field definition, help_text included, and compares it
    against the model class. An f-string over a per-deployment setting is evaluated
    once at import, so whichever site generated the migration baked its own numbers
    into shared history and every other site drifted forever. Keep values that vary
    by deployment out of field definitions entirely.
    """

    #: The autodetector reads migration files, not tables — MigrationLoader is
    #: given no connection below.
    databases = []

    def test_models_match_migration_state(self):
        loader = MigrationLoader(None, ignore_no_migrations=True)
        autodetector = MigrationAutodetector(
            loader.project_state(),
            ProjectState.from_apps(apps),
            NonInteractiveMigrationQuestioner(),
        )
        drifted = [
            f"{app_label}.{op.model_name}.{op.name}"
            for app_label, migrations in autodetector._detect_changes().items()
            for migration in migrations
            for op in migration.operations
        ]
        self.assertEqual(drifted, [])


class UploadLimitsFollowSettingsTests(SimpleTestCase):
    """The upload dimensions are read per request, not bound at import.

    `screens/models/source.py` used to do `from advertising.settings import ...`,
    which ignores DJANGO_SETTINGS_MODULE and defeats override_settings — that is
    how one developer's numbers ended up in the shipped help screenshots.
    """

    databases = []

    @override_settings(MAX_IMG_WIDTH=4321, MAX_IMG_HEIGHT=1234)
    def test_field_hint_follows_overridden_settings(self):
        self.assertEqual(
            file_help_text(),
            "resolution of files should be 4321x1234, videos must be mp4",
        )

    @override_settings(MAX_IMG_WIDTH=4321, MAX_IMG_HEIGHT=1234)
    def test_add_form_hint_follows_overridden_settings(self):
        """The rendered `file` hint carries the dimensions the model field no longer does."""
        # Neither form declares Meta.model — SourceDisplay.get_form builds them
        # through modelform_factory, so do the same rather than instantiating bare.
        form = modelform_factory(Source, form=PlaylistAssigningSourceForm, fields=("file",))()
        self.assertEqual(
            form.fields["file"].help_text,
            "resolution of files should be 4321x1234, videos must be mp4",
        )

    @override_settings(MAX_IMG_WIDTH=4321, MAX_IMG_HEIGHT=1234)
    def test_bulk_upload_hint_follows_overridden_settings(self):
        # The bulk branch excludes `file`, which is what the parent's
        # `if "file" in self.fields` guard exists for.
        form = modelform_factory(
            Source, form=SourceBulkCreateForm, exclude=("file", "name"),
        )()
        self.assertNotIn("file", form.fields)
        self.assertIn("4321x1234", form.fields["files"].help_text)

    def test_hint_is_not_stored_on_the_model_field(self):
        """The dimensions must not reach the field — that is what migration state records."""
        field_help = Source._meta.get_field("file").help_text
        self.assertNotIn(str(settings.MAX_IMG_WIDTH), field_help)
        self.assertNotIn(str(settings.MAX_IMG_HEIGHT), field_help)
