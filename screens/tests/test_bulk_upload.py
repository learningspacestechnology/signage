"""Bulk upload: one Source per file, each owned, placed and checked like a single upload.

The form saves its one instance again under a new pk for every file, so
anything the admin did to ``form.instance`` afterwards -- attaching the active
team -- reached only the last file. The others were saved with no team and
vanished for everyone but a superuser viewing all teams. The file checks were
skipped wholesale too: ``Source.clean`` has no single file to look at, so an
oversize image went straight onto the screens.
"""
import io

from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from PIL import Image

from screens.models import Playlist, PlaylistEntry, Source, Team

BULK_URL = "/admin/screens/source/bulk_create/"

# Uploads stay in memory rather than landing in the developer's MEDIA_ROOT.
IN_MEMORY_STORAGE = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


def image(name, size=(10, 10)):
    buffer = io.BytesIO()
    Image.new("RGB", size).save(buffer, "PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def video(name):
    return SimpleUploadedFile(name, b"not really a video", content_type="video/mp4")


def form_errors(response):
    return response.context["adminform"].form.errors


@override_settings(STORAGES=IN_MEMORY_STORAGE, MAX_IMG_WIDTH=100, MAX_IMG_HEIGHT=50)
class BulkUploadTests(TestCase):
    def setUp(self):
        Team.objects.all().delete()
        self.alpha = Team.objects.create(name="Alpha")
        self.bravo = Team.objects.create(name="Bravo")

        self.operator = User.objects.create_user("op", "op@x", "pw", is_staff=True)
        self.operator.teams.add(self.alpha)
        for model in (Source, Playlist, PlaylistEntry):
            self.operator.user_permissions.add(*Permission.objects.filter(
                content_type=ContentType.objects.get_for_model(model)))
        self.root = User.objects.create_superuser("root", "r@x", "pw")

        self.posters = Playlist.objects.create(name="Posters")
        self.notices = Playlist.objects.create(name="Notices")
        for playlist in (self.posters, self.notices):
            playlist.teams.add(self.alpha)

    def client_for(self, user, active_team=None):
        client = Client()
        client.force_login(user)
        if active_team is not None:
            client.get(f"/admin/set-active-team/{active_team.pk}/")
        return client

    def upload(self, client, files, source_type=Source.IMAGE, playlists=(), **extra):
        return client.post(BULK_URL, {
            "type": source_type,
            "playlists": [playlist.pk for playlist in playlists],
            "files": files,
            "_save": "Save",
            **extra,
        })

    def assert_batch(self, names, teams, playlists):
        sources = Source.objects.order_by("name")
        self.assertEqual([s.name for s in sources], sorted(names))
        for source in sources:
            with self.subTest(source=source.name):
                self.assertEqual(set(source.teams.all()), set(teams))
                self.assertEqual(set(source.playlists.all()), set(playlists))

    # --- Every file is owned and placed -------------------------------------

    def test_every_file_gets_the_operators_team_and_playlists(self):
        response = self.upload(self.client_for(self.operator),
                               [image("a.png"), image("b.png"), image("c.png")],
                               playlists=[self.posters, self.notices])
        self.assertEqual(response.status_code, 302)
        self.assert_batch(["a.png", "b.png", "c.png"],
                          teams=[self.alpha], playlists=[self.posters, self.notices])
        self.assertEqual(
            set(PlaylistEntry.objects.values_list("number", flat=True)), {10})
        self.assertEqual(PlaylistEntry.objects.count(), 6)

    def test_every_file_shows_in_the_operators_content_list(self):
        client = self.client_for(self.operator)
        self.upload(client, [image("a.png"), image("b.png"), image("c.png")],
                    playlists=[self.posters])
        for url in ("/admin/screens/source/",
                    f"/admin/screens/source/?playlist={self.posters.pk}"):
            response = client.get(url)
            for name in ("a.png", "b.png", "c.png"):
                with self.subTest(url=url, name=name):
                    self.assertContains(response, name)

    def test_superuser_with_a_team_selected_gives_it_to_every_file(self):
        response = self.upload(self.client_for(self.root, active_team=self.bravo),
                               [image("a.png"), image("b.png")], playlists=[self.posters])
        self.assertEqual(response.status_code, 302)
        self.assert_batch(["a.png", "b.png"], teams=[self.bravo], playlists=[self.posters])

    def test_superuser_under_all_teams_gives_every_file_the_ticked_teams(self):
        response = self.upload(self.client_for(self.root),
                               [image("a.png"), image("b.png")], playlists=[self.posters],
                               teams=[self.alpha.pk])
        self.assertEqual(response.status_code, 302)
        self.assert_batch(["a.png", "b.png"], teams=[self.alpha], playlists=[self.posters])

    def test_every_file_records_its_uploader_dates_and_size(self):
        response = self.upload(self.client_for(self.operator),
                               [image("a.png", (100, 50)), image("b.png", (20, 30))],
                               valid_from_0="2026-12-01", valid_from_1="09:00:00",
                               expires_at_0="2026-12-31", expires_at_1="17:00:00")
        self.assertEqual(response.status_code, 302)
        sizes = {s.name: (s.width, s.height) for s in Source.objects.all()}
        self.assertEqual(sizes, {"a.png": (100, 50), "b.png": (20, 30)})
        for source in Source.objects.all():
            with self.subTest(source=source.name):
                self.assertEqual(source.created_by, self.operator)
                self.assertEqual(source.valid_from.date().isoformat(), "2026-12-01")
                self.assertEqual(source.expires_at.date().isoformat(), "2026-12-31")

    # --- Every file is checked, and one bad file stops the batch ------------

    def test_an_oversize_image_rejects_the_whole_batch(self):
        response = self.upload(self.client_for(self.operator),
                               [image("fine.png"), image("wide.png", (101, 50))])
        self.assertEqual(response.status_code, 200)
        self.assertIn("wide.png: Image resolution must be at most 100x50",
                      form_errors(response)["files"])
        self.assertFalse(Source.objects.exists())

    def test_every_bad_file_is_named(self):
        response = self.upload(self.client_for(self.operator),
                               [image("wide.png", (101, 50)), image("fine.png"),
                                image("tall.png", (100, 51))])
        errors = form_errors(response)["files"]
        self.assertEqual(errors, [
            "wide.png: Image resolution must be at most 100x50",
            "tall.png: Image resolution must be at most 100x50",
        ])

    def test_an_image_at_the_limit_is_accepted(self):
        response = self.upload(self.client_for(self.operator), [image("exact.png", (100, 50))])
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Source.objects.count(), 1)

    def test_a_file_that_is_not_an_image_rejects_an_image_batch(self):
        notes = SimpleUploadedFile("notes.txt", b"plain text")
        response = self.upload(self.client_for(self.operator), [image("fine.png"), notes])
        self.assertEqual(response.status_code, 200)
        [error] = form_errors(response)["files"]
        self.assertTrue(error.startswith("notes.txt: Error opening image file"), error)
        self.assertFalse(Source.objects.exists())

    def test_a_non_mp4_file_rejects_a_video_batch(self):
        response = self.upload(self.client_for(self.operator),
                               [video("clip.mp4"), image("poster.png")],
                               source_type=Source.VIDEO)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(form_errors(response)["files"],
                         ["poster.png: Video files must have .mp4 extensions"])
        self.assertFalse(Source.objects.exists())

    def test_a_video_batch_of_mp4s_is_accepted(self):
        response = self.upload(self.client_for(self.operator),
                               [video("one.mp4"), video("two.mp4")],
                               source_type=Source.VIDEO, playlists=[self.posters])
        self.assertEqual(response.status_code, 302)
        self.assert_batch(["one.mp4", "two.mp4"], teams=[self.alpha], playlists=[self.posters])

    def test_website_is_not_offered(self):
        client = self.client_for(self.operator)
        form = client.get(BULK_URL).context["adminform"].form
        self.assertNotIn(Source.IFRAME, [value for value, _ in form.fields["type"].choices])
        self.assertNotIn("url", form.fields)

        response = self.upload(client, [image("a.png")], source_type=Source.IFRAME)
        self.assertEqual(response.status_code, 200)
        self.assertIn("type", form_errors(response))
        self.assertFalse(Source.objects.exists())

    def test_the_bulk_fields_do_not_leak_into_the_single_add_form(self):
        """The excluded fields are worked out per request, not stored on the admin."""
        client = self.client_for(self.operator)
        client.get(BULK_URL)
        fields = client.get("/admin/screens/source/add/").context["adminform"].form.fields
        self.assertIn("file", fields)
        self.assertIn("name", fields)
        self.assertIn("url", fields)

    def test_an_anonymous_visitor_is_sent_to_log_in(self):
        response = Client().get(BULK_URL)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    # --- The single upload form ----------------------------------------------

    def test_single_upload_reports_an_oversize_image_plainly(self):
        """The resolution error used to be caught and re-wrapped as a failure to open."""
        response = self.client_for(self.operator).post("/admin/screens/source/add/", {
            "name": "Wide",
            "type": Source.IMAGE,
            "file": image("wide.png", (101, 50)),
            "_save": "Save",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(form_errors(response)["file"],
                         ["Image resolution must be at most 100x50"])
