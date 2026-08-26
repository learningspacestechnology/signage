"""The upload size hint reaches the admin pages, and follows the current settings.

``MAX_IMG_WIDTH``/``MAX_IMG_HEIGHT`` are per-deployment, so they must not live on
``Source.file`` — anything in a field definition is recorded in migration state,
where no value can be right for every site. They are applied by the forms instead
(``screens/forms.py``), which is a layer these tests exist to keep honest: moving
text off a model and into a form is exactly the change that silently renders
nothing.
"""
from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings

from screens.models import Team


class UploadHintRenderingTests(TestCase):
    def setUp(self):
        self.team = Team.objects.create(name="Alpha")
        self.admin = User.objects.create_superuser(
            username="root", email="root@example.com", password="rootpw",
        )
        self.client = Client()
        self.client.force_login(self.admin)

    @override_settings(MAX_IMG_WIDTH=4321, MAX_IMG_HEIGHT=1234)
    def test_add_form_shows_the_resolution_hint(self):
        response = self.client.get("/admin/screens/source/add/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "resolution of files should be 4321x1234, videos must be mp4",
        )

    @override_settings(MAX_IMG_WIDTH=4321, MAX_IMG_HEIGHT=1234)
    def test_bulk_upload_form_shows_the_resolution_hint(self):
        response = self.client.get("/admin/screens/source/bulk_create/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Images must be at most 4321x1234")

    def test_hint_tracks_a_changed_setting(self):
        """Two different settings, two different pages — nothing is baked at import."""
        with override_settings(MAX_IMG_WIDTH=1920, MAX_IMG_HEIGHT=1080):
            self.assertContains(
                self.client.get("/admin/screens/source/add/"), "1920x1080",
            )
        with override_settings(MAX_IMG_WIDTH=2160, MAX_IMG_HEIGHT=3840):
            self.assertContains(
                self.client.get("/admin/screens/source/add/"), "2160x3840",
            )
