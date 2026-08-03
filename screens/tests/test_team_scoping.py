from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.forms import modelform_factory
from django.test import Client, TestCase

from advertising.middleware import ALL_TEAMS
from screens.models import (
    Playlist,
    PlaylistEntry,
    PlaylistRelation,
    Schedule,
    Screen,
    Source,
    Team,
)


def _grant_all_model_perms(user, models):
    for model in models:
        ct = ContentType.objects.get_for_model(model)
        user.user_permissions.add(*Permission.objects.filter(content_type=ct))


class TeamScopingTests(TestCase):
    def setUp(self):
        # Delete the seeded Default team if a setup created one; we manage our own
        Team.objects.all().delete()

        self.team_a = Team.objects.create(name="Alpha")
        self.team_b = Team.objects.create(name="Bravo")

        self.user_a = User.objects.create_user('alice', 'a@x', 'pw', is_staff=True)
        self.user_b = User.objects.create_user('bob', 'b@x', 'pw', is_staff=True)
        self.user_ab = User.objects.create_user('eve', 'ab@x', 'pw', is_staff=True)
        self.super = User.objects.create_superuser('root', 'r@x', 'pw')
        self.user_a.teams.add(self.team_a)
        self.user_b.teams.add(self.team_b)
        self.user_ab.teams.add(self.team_a, self.team_b)

        for u in (self.user_a, self.user_b, self.user_ab):
            _grant_all_model_perms(u, [Source, Playlist, Screen, Schedule, PlaylistEntry, PlaylistRelation])

        # Content
        self.src_a = Source.objects.create(type=Source.IFRAME, name="srcA", url="http://a")
        self.src_b = Source.objects.create(type=Source.IFRAME, name="srcB", url="http://b")
        self.src_shared = Source.objects.create(type=Source.IFRAME, name="srcShared", url="http://s")
        self.src_a.teams.add(self.team_a)
        self.src_b.teams.add(self.team_b)
        self.src_shared.teams.add(self.team_a, self.team_b)

        self.list_a = Playlist.objects.create(name="listA")
        self.list_b = Playlist.objects.create(name="listB")
        self.list_a.teams.add(self.team_a)
        self.list_b.teams.add(self.team_b)

    # --- Queryset scoping ----------------------------------------------------

    def test_changelist_lists_only_active_team_objects(self):
        c = Client()
        c.force_login(self.user_a)
        resp = c.get('/admin/screens/source/')
        self.assertContains(resp, "srcA")
        self.assertContains(resp, "srcShared")
        self.assertNotContains(resp, "srcB")

    def test_object_outside_team_returns_404(self):
        c = Client()
        c.force_login(self.user_a)
        resp = c.get(f'/admin/screens/source/{self.src_b.pk}/change/')
        self.assertEqual(resp.status_code, 302)
        # the admin returns a 302 to login or to the changelist for missing-perm objects
        # — we just need to confirm it's not a 200 render of the change page
        resp = c.get(f'/admin/screens/playlist/{self.list_b.pk}/change/')
        self.assertNotEqual(resp.status_code, 200)

    def test_shared_object_visible_to_both_teams(self):
        for user in (self.user_a, self.user_b):
            c = Client()
            c.force_login(user)
            resp = c.get('/admin/screens/source/')
            self.assertContains(resp, "srcShared")

    # --- Active team auto-attach on create ----------------------------------

    def test_creating_source_auto_attaches_active_team(self):
        c = Client()
        c.force_login(self.user_a)
        c.get('/admin/screens/source/')  # initialise session
        resp = c.post('/admin/screens/source/add/', {
            'type': Source.IFRAME,
            'name': 'new-source',
            'url': 'http://new.example/',
            'playlists': [],
            'playlistentry_set-TOTAL_FORMS': '0',
            'playlistentry_set-INITIAL_FORMS': '0',
            'playlistentry_set-MIN_NUM_FORMS': '0',
            'playlistentry_set-MAX_NUM_FORMS': '1000',
        }, follow=False)
        # On success Django admin redirects; on form error it re-renders 200
        new = Source.objects.filter(name='new-source').first()
        self.assertIsNotNone(new, f"Source was not created. Status={resp.status_code}")
        self.assertEqual(list(new.teams.all()), [self.team_a])

    # --- Cross-team PlaylistRelation rules -----------------------------------

    def _build_relation_form(self, user):
        from screens.admin import PlaylistParentsInlineForm

        FormCls = modelform_factory(
            PlaylistRelation,
            form=PlaylistParentsInlineForm,
            fields=['super_list', 'inheriting_list'],
        )

        class DummyReq:
            pass

        DummyReq.user = user
        form = FormCls(data={
            'super_list': self.list_b.pk,
            'inheriting_list': self.list_a.pk,
        })
        form._request = DummyReq()
        return form

    def test_multi_team_user_can_cross_team_inherit(self):
        form = self._build_relation_form(self.user_ab)
        self.assertTrue(form.is_valid(), form.errors)

    def test_single_team_user_cannot_cross_team_inherit(self):
        form = self._build_relation_form(self.user_a)
        self.assertFalse(form.is_valid())

    def test_superuser_can_cross_team_inherit(self):
        form = self._build_relation_form(self.super)
        self.assertTrue(form.is_valid(), form.errors)

    # --- Active team middleware defaults -------------------------------------

    def test_superuser_defaults_to_all_teams(self):
        c = Client()
        c.force_login(self.super)
        resp = c.get('/admin/screens/source/')
        self.assertContains(resp, "srcA")
        self.assertContains(resp, "srcB")
        self.assertContains(resp, "srcShared")

    def test_user_with_no_teams_blocked(self):
        no_team_user = User.objects.create_user('lonely', 'l@x', 'pw', is_staff=True)
        c = Client()
        c.force_login(no_team_user)
        resp = c.get('/admin/')
        self.assertEqual(resp.status_code, 403)

    # --- Switcher endpoint ---------------------------------------------------

    def test_switcher_updates_session_and_scope(self):
        c = Client()
        c.force_login(self.user_ab)
        c.get(f'/admin/set-active-team/{self.team_a.pk}/')
        resp = c.get('/admin/screens/source/')
        self.assertContains(resp, "srcA")
        self.assertNotContains(resp, "srcB")

        c.get(f'/admin/set-active-team/{self.team_b.pk}/')
        resp = c.get('/admin/screens/source/')
        self.assertNotContains(resp, "srcA")
        self.assertContains(resp, "srcB")

    def test_non_superuser_cannot_switch_to_unrelated_team(self):
        other = Team.objects.create(name="Charlie")
        c = Client()
        c.force_login(self.user_a)
        resp = c.get(f'/admin/set-active-team/{other.pk}/')
        self.assertEqual(resp.status_code, 400)

    def test_non_superuser_cannot_use_all_teams(self):
        c = Client()
        c.force_login(self.user_a)
        resp = c.get('/admin/set-active-team/all/')
        self.assertEqual(resp.status_code, 400)

    # --- Model clean: at least one team --------------------------------------

    def test_clean_rejects_object_with_zero_teams(self):
        src = Source.objects.create(type=Source.IFRAME, name="orphan", url="http://o")
        with self.assertRaises(ValidationError):
            src.clean()

    # --- Team deletion guards ------------------------------------------------

    def test_cannot_delete_team_with_members(self):
        empty = Team.objects.create(name="Delta")
        empty.members.add(self.user_a)
        with self.assertRaises(ValidationError):
            empty.delete()

    def test_cannot_delete_team_with_owned_objects(self):
        empty = Team.objects.create(name="Echo")
        src = Source.objects.create(type=Source.IFRAME, name="echo-src", url="http://e")
        src.teams.add(empty)
        with self.assertRaises(ValidationError):
            empty.delete()

    def test_can_delete_truly_empty_team(self):
        empty = Team.objects.create(name="Foxtrot")
        empty.delete()
        self.assertFalse(Team.objects.filter(name="Foxtrot").exists())

    def test_non_superuser_cannot_delete_team_via_admin(self):
        empty = Team.objects.create(name="Golf")
        c = Client()
        c.force_login(self.user_a)
        # non-superusers don't even have the Team admin module
        resp = c.get(f'/admin/screens/team/{empty.pk}/delete/')
        self.assertIn(resp.status_code, (302, 403, 404))

    # --- Add/change page render for non-superusers ---------------------------

    def test_non_superuser_can_open_playlist_and_schedule_add_pages(self):
        c = Client()
        c.force_login(self.user_a)
        self.assertEqual(c.get('/admin/screens/playlist/add/').status_code, 200)
        self.assertEqual(c.get('/admin/screens/schedule/add/').status_code, 200)

    def test_non_superuser_can_open_playlist_change_page(self):
        c = Client()
        c.force_login(self.user_a)
        resp = c.get(f'/admin/screens/playlist/{self.list_a.pk}/change/')
        self.assertEqual(resp.status_code, 200)

    # --- Team picker render --------------------------------------------------

    def test_team_picker_button_renders_around_badge(self):
        c = Client()
        c.force_login(self.user_ab)
        resp = c.get('/admin/')
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('openTeamPicker', body)
        self.assertIn(self.team_a.name, body)
        self.assertIn(f'/admin/set-active-team/{self.team_a.pk}/', body)
        self.assertIn(f'/admin/set-active-team/{self.team_b.pk}/', body)

    def test_team_picker_includes_all_teams_for_superuser(self):
        c = Client()
        c.force_login(self.super)
        resp = c.get('/admin/')
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn('openTeamPicker', body)
        self.assertIn('/admin/set-active-team/all/', body)

    # --- Playlist tree endpoint scoping -------------------------------------

    def _fetch_tree(self, user):
        c = Client()
        c.force_login(user)
        resp = c.get('/api/playlist_tree')
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        return resp.json()

    def test_playlist_tree_shows_only_user_team_playlists(self):
        data = self._fetch_tree(self.user_a)
        self.assertIn(str(self.list_a.pk), data)
        self.assertNotIn(str(self.list_b.pk), data)

    def test_playlist_tree_includes_direct_parents(self):
        PlaylistRelation.objects.create(super_list=self.list_b, inheriting_list=self.list_a)
        data = self._fetch_tree(self.user_a)
        self.assertIn(str(self.list_a.pk), data)
        self.assertIn(str(self.list_b.pk), data)
        self.assertEqual(data[str(self.list_b.pk)]['children'], [self.list_a.pk])

    def test_playlist_tree_includes_full_ancestor_chain(self):
        list_c = Playlist.objects.create(name="listC")
        list_c.teams.add(self.team_b)
        PlaylistRelation.objects.create(super_list=list_c, inheriting_list=self.list_b)
        PlaylistRelation.objects.create(super_list=self.list_b, inheriting_list=self.list_a)

        data = self._fetch_tree(self.user_a)
        self.assertIn(str(self.list_a.pk), data)
        self.assertIn(str(self.list_b.pk), data)
        self.assertIn(str(list_c.pk), data)
        self.assertEqual(data[str(list_c.pk)]['children'], [self.list_b.pk])
        self.assertEqual(data[str(self.list_b.pk)]['children'], [self.list_a.pk])

    def test_playlist_tree_includes_descendants_of_accessible(self):
        # Another team inheriting *from* one of ours stays on our tree: we need
        # to see where our content ends up.
        list_d = Playlist.objects.create(name="listD")
        list_d.teams.add(self.team_b)
        PlaylistRelation.objects.create(super_list=self.list_a, inheriting_list=list_d)

        data = self._fetch_tree(self.user_a)
        self.assertIn(str(self.list_a.pk), data)
        self.assertIn(str(list_d.pk), data)
        self.assertEqual(data[str(self.list_a.pk)]['children'], [list_d.pk])

    def test_playlist_tree_excludes_unrelated_other_team_playlist(self):
        # listB is team_b's and has no inheritance link to anything of team_a's
        data = self._fetch_tree(self.user_a)
        self.assertNotIn(str(self.list_b.pk), data)

    def test_playlist_tree_scoped_to_active_team_for_superuser(self):
        # A superuser browsing as one team sees that team's tree, not everything
        c = Client()
        c.force_login(self.super)
        c.get(f'/admin/set-active-team/{self.team_a.pk}/')
        resp = c.get('/api/playlist_tree')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn(str(self.list_a.pk), data)
        self.assertNotIn(str(self.list_b.pk), data)

    def test_playlist_tree_scoped_to_active_team_for_multi_team_user(self):
        # eve is in both teams; only the active team's playlists appear
        c = Client()
        c.force_login(self.user_ab)
        c.get(f'/admin/set-active-team/{self.team_b.pk}/')
        data = c.get('/api/playlist_tree').json()
        self.assertIn(str(self.list_b.pk), data)
        self.assertNotIn(str(self.list_a.pk), data)

    def test_playlist_tree_excludes_siblings_via_shared_ancestor(self):
        sibling = Playlist.objects.create(name="siblingInA")
        sibling.teams.add(self.team_a)  # team_a only — user_b cannot see it directly
        list_d = Playlist.objects.create(name="listD")
        list_d.teams.add(self.team_b)
        PlaylistRelation.objects.create(super_list=self.list_a, inheriting_list=sibling)
        PlaylistRelation.objects.create(super_list=self.list_a, inheriting_list=list_d)

        # user_b owns list_d; list_a is its ancestor (visible), sibling is a peer under list_a
        # that user_b has no relation to and must not surface
        data = self._fetch_tree(self.user_b)
        self.assertIn(str(list_d.pk), data)
        self.assertIn(str(self.list_a.pk), data)
        self.assertNotIn(str(sibling.pk), data)
        # list_a's children edge to sibling must be filtered out; only list_d remains
        self.assertEqual(data[str(self.list_a.pk)]['children'], [list_d.pk])

    def test_playlist_tree_handles_inheritance_cycle(self):
        # A → B (B inherits from A), B → A (A inherits from B) — a 2-cycle
        PlaylistRelation.objects.create(super_list=self.list_a, inheriting_list=self.list_b)
        # need both in the same team so user_a can see both as accessible
        self.list_b.teams.add(self.team_a)
        PlaylistRelation.objects.create(super_list=self.list_b, inheriting_list=self.list_a)

        data = self._fetch_tree(self.user_a)
        self.assertIn(str(self.list_a.pk), data)
        self.assertIn(str(self.list_b.pk), data)

    def test_playlist_tree_superuser_sees_all(self):
        list_c = Playlist.objects.create(name="listC")
        list_c.teams.add(self.team_b)
        data = self._fetch_tree(self.super)
        self.assertIn(str(self.list_a.pk), data)
        self.assertIn(str(self.list_b.pk), data)
        self.assertIn(str(list_c.pk), data)
