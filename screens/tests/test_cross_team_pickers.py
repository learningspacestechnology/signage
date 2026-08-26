"""An object two teams share may point at content only one of them owns.

Scoping the pickers to the viewer's team used to drop that value from the
choices, so the field rendered blank and the form could not be saved at all
without repointing it — silently changing what the other team's screens show.
The value is now kept, flagged as another team's, and warned about.
"""

import datetime
import re

import recurrence
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase

from screens.models import (
    Playlist,
    PlaylistEntry,
    PlaylistRelation,
    Schedule,
    ScheduleRule,
    Screen,
    Source,
    Team,
)


def _grant_all_model_perms(user, models):
    for model in models:
        ct = ContentType.objects.get_for_model(model)
        user.user_permissions.add(*Permission.objects.filter(content_type=ct))


def _select_options(html, name):
    """The <option> markup of the named select, or None if it is absent."""
    match = re.search(rf'<select[^>]*name="{name}".*?</select>', html, re.S)
    if match is None:
        return None
    return re.findall(r'<option[^>]*>[^<]*</option>', match.group(0))


def _selected_option(html, name):
    options = _select_options(html, name) or []
    return next((o for o in options if 'selected' in o), None)


def _errors(response):
    return [
        re.sub(r'<[^>]+>', ' ', e).strip()
        for e in re.findall(r'<ul class="errorlist[^"]*">.*?</ul>',
                            response.content.decode(), re.S)
    ]


class CrossTeamPickerTests(TestCase):
    def setUp(self):
        Team.objects.all().delete()
        self.team_a = Team.objects.create(name="Alpha")
        self.team_b = Team.objects.create(name="Bravo")

        self.user_a = User.objects.create_user('alice', 'a@x', 'pw', is_staff=True)
        self.user_a.teams.add(self.team_a)
        self.user_ab = User.objects.create_user('eve', 'ab@x', 'pw', is_staff=True)
        self.user_ab.teams.add(self.team_a, self.team_b)
        self.super = User.objects.create_superuser('root', 'r@x', 'pw')
        for user in (self.user_a, self.user_ab):
            _grant_all_model_perms(user, [
                Source, Playlist, Screen, Schedule, ScheduleRule,
                PlaylistEntry, PlaylistRelation,
            ])

        self.list_a = Playlist.objects.create(name="listA")
        self.list_a.teams.add(self.team_a)
        self.list_b = Playlist.objects.create(name="listB")
        self.list_b.teams.add(self.team_b)
        # Bravo content that is NOT referenced by anything shared: must stay out
        # of every picker, or the fix would have opened a hole.
        self.list_b_other = Playlist.objects.create(name="listBOther")
        self.list_b_other.teams.add(self.team_b)

        self.client_a = Client()
        self.client_a.force_login(self.user_a)

    # --- Schedule.default_playlist ------------------------------------------

    def _shared_schedule(self):
        sched = Schedule.objects.create(name="shared", default_playlist=self.list_b)
        sched.teams.add(self.team_a, self.team_b)
        return sched

    def _schedule_post(self, sched, playlist_pk, rules=0, **extra):
        post = {
            'name': sched.name,
            'description': '',
            'default_playlist': str(playlist_pk),
            'schedulerule_set-TOTAL_FORMS': str(rules),
            'schedulerule_set-INITIAL_FORMS': str(rules),
            'schedulerule_set-MIN_NUM_FORMS': '0',
            'schedulerule_set-MAX_NUM_FORMS': '1000',
            '_save': 'Save',
        }
        post.update(extra)
        return post

    def test_foreign_default_playlist_stays_selected_and_labelled(self):
        sched = self._shared_schedule()
        resp = self.client_a.get(f'/admin/screens/schedule/{sched.pk}/change/')
        selected = _selected_option(resp.content.decode(), 'default_playlist')
        self.assertIsNotNone(selected, "the value already set must be selectable")
        self.assertIn("listB", selected)
        self.assertIn("another team: Bravo", selected)

    def test_foreign_default_playlist_warns_in_help_text(self):
        sched = self._shared_schedule()
        resp = self.client_a.get(f'/admin/screens/schedule/{sched.pk}/change/')
        self.assertContains(resp, "owned by another team (Bravo)")
        self.assertContains(resp, "Leaving it alone keeps it as it is")
        self.assertContains(resp, "screens show")

    def test_other_teams_unreferenced_playlist_stays_out_of_the_picker(self):
        sched = self._shared_schedule()
        resp = self.client_a.get(f'/admin/screens/schedule/{sched.pk}/change/')
        options = _select_options(resp.content.decode(), 'default_playlist')
        self.assertTrue(any("listA" in o for o in options))
        self.assertFalse(any("listBOther" in o for o in options))

    def test_resaving_keeps_the_foreign_default_playlist(self):
        sched = self._shared_schedule()
        resp = self.client_a.post(
            f'/admin/screens/schedule/{sched.pk}/change/',
            self._schedule_post(sched, self.list_b.pk, name="renamed"),
        )
        self.assertEqual(resp.status_code, 302, _errors(resp))
        sched.refresh_from_db()
        self.assertEqual(sched.default_playlist, self.list_b)

    def test_editing_another_field_no_longer_blocks_on_the_playlist(self):
        """The regression this fixes: the form was unsaveable in every direction."""
        sched = self._shared_schedule()
        post = self._schedule_post(sched, self.list_b.pk)
        post['name'] = 'renamed via unrelated edit'
        resp = self.client_a.post(f'/admin/screens/schedule/{sched.pk}/change/', post)
        self.assertEqual(resp.status_code, 302, _errors(resp))
        sched.refresh_from_db()
        self.assertEqual(sched.name, 'renamed via unrelated edit')
        self.assertEqual(sched.default_playlist, self.list_b)

    def test_repointing_at_own_team_still_allowed(self):
        sched = self._shared_schedule()
        resp = self.client_a.post(
            f'/admin/screens/schedule/{sched.pk}/change/',
            self._schedule_post(sched, self.list_a.pk),
        )
        self.assertEqual(resp.status_code, 302, _errors(resp))
        sched.refresh_from_db()
        self.assertEqual(sched.default_playlist, self.list_a)

    def test_unreferenced_other_team_playlist_still_rejected_on_post(self):
        sched = self._shared_schedule()
        resp = self.client_a.post(
            f'/admin/screens/schedule/{sched.pk}/change/',
            self._schedule_post(sched, self.list_b_other.pk),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Select a valid choice. That choice is not one of the "
                      "available choices.", " ".join(_errors(resp)))
        sched.refresh_from_db()
        self.assertEqual(sched.default_playlist, self.list_b)

    def test_add_form_offers_only_own_team(self):
        resp = self.client_a.get('/admin/screens/schedule/add/')
        options = _select_options(resp.content.decode(), 'default_playlist')
        self.assertTrue(any("listA" in o for o in options))
        self.assertFalse(any("listB" in o for o in options))

    # --- ScheduleRule.playlist (inline) --------------------------------------

    def test_foreign_rule_playlist_survives_a_save(self):
        sched = self._shared_schedule()
        sched.default_playlist = self.list_a
        sched.save()
        rule = ScheduleRule.objects.create(
            schedule=sched, playlist=self.list_b,
            starts=datetime.date(2020, 1, 1),
            occurrences=recurrence.Recurrence(
                rrules=[recurrence.Rule(recurrence.DAILY)]),
            start_time=datetime.time(9), end_time=datetime.time(17), priority=1,
        )
        resp = self.client_a.get(f'/admin/screens/schedule/{sched.pk}/change/')
        selected = _selected_option(resp.content.decode(),
                                    'schedulerule_set-0-playlist')
        self.assertIsNotNone(selected)
        self.assertIn("another team: Bravo", selected)

        post = self._schedule_post(sched, self.list_a.pk, rules=1, **{
            'schedulerule_set-0-id': str(rule.pk),
            'schedulerule_set-0-schedule': str(sched.pk),
            'schedulerule_set-0-playlist': str(self.list_b.pk),
            'schedulerule_set-0-starts': '2020-01-01',
            'schedulerule_set-0-occurrences': 'RRULE:FREQ=DAILY',
            'schedulerule_set-0-start_time': '09:00:00',
            'schedulerule_set-0-end_time': '17:00:00',
            'schedulerule_set-0-priority': '1',
        })
        resp = self.client_a.post(f'/admin/screens/schedule/{sched.pk}/change/', post)
        self.assertEqual(resp.status_code, 302, _errors(resp))
        rule.refresh_from_db()
        self.assertEqual(rule.playlist, self.list_b)

    # --- Screen: nullable FKs were dropped silently rather than erroring -----

    def test_foreign_interspersed_playlist_is_not_silently_cleared(self):
        sched_a = Schedule.objects.create(name="schedA", default_playlist=self.list_a)
        sched_a.teams.add(self.team_a)
        screen = Screen.objects.create(
            name="shared screen", ip="10.0.0.9", schedule=sched_a,
            interspersed_playlist=self.list_b)
        screen.teams.add(self.team_a, self.team_b)
        resp = self.client_a.get(f'/admin/screens/screen/{screen.pk}/change/')
        selected = _selected_option(resp.content.decode(), 'interspersed_playlist')
        self.assertIsNotNone(selected)
        self.assertIn("another team: Bravo", selected)

        resp = self.client_a.post(f'/admin/screens/screen/{screen.pk}/change/', {
            'name': screen.name,
            'ip': screen.ip,
            'schedule': str(sched_a.pk),
            'interspersed_playlist': str(self.list_b.pk),
            'interspersed_rate': '1',
            'ticker_enabled': '',
            'ticker_layout': screen.ticker_layout,
            'ticker_text': '',
            'ticker_style_preset': screen.ticker_style_preset,
            'ticker_font_size_px': '',
            'ticker_font_color': '',
            'ticker_background_color': '',
            'ticker_background_opacity': '',
            'ticker_scroll_speed_px_sec': '',
            '_save': 'Save',
        })
        self.assertEqual(resp.status_code, 302, _errors(resp))
        screen.refresh_from_db()
        self.assertEqual(screen.interspersed_playlist, self.list_b)

    # --- PlaylistEntry.source (inline, scoped to the user's teams) -----------

    def test_foreign_entry_source_survives_a_save(self):
        src_b = Source.objects.create(type=Source.IFRAME, name="srcB", url="http://example.com/b")
        src_b.teams.add(self.team_b)
        shared = Playlist.objects.create(name="sharedList")
        shared.teams.add(self.team_a, self.team_b)
        entry = PlaylistEntry.objects.create(playlist=shared, source=src_b, number=1)

        resp = self.client_a.get(f'/admin/screens/playlist/{shared.pk}/change/')
        selected = _selected_option(resp.content.decode(),
                                    'playlistentry_set-0-source')
        self.assertIsNotNone(selected)
        self.assertIn("another team: Bravo", selected)
        entry.refresh_from_db()
        self.assertEqual(entry.source, src_b)

    # --- PlaylistRelation.super_list (inline + its own clean()) -------------

    def test_foreign_parent_relation_can_be_resaved(self):
        shared = Playlist.objects.create(name="sharedList")
        shared.teams.add(self.team_a, self.team_b)
        rel = PlaylistRelation.objects.create(
            inheriting_list=shared, super_list=self.list_b)

        resp = self.client_a.get(f'/admin/screens/playlist/{shared.pk}/change/')
        html = resp.content.decode()
        selected = _selected_option(html, 'parents_list-0-super_list')
        self.assertIsNotNone(selected)
        self.assertIn("another team: Bravo", selected)

        resp = self.client_a.post(f'/admin/screens/playlist/{shared.pk}/change/', {
            'name': shared.name,
            'description': '',
            'default_duration': '10',
            'interspersed_playlist': '',
            'interspersed_rate': '1',
            'parents_list-TOTAL_FORMS': '1',
            'parents_list-INITIAL_FORMS': '1',
            'parents_list-MIN_NUM_FORMS': '0',
            'parents_list-MAX_NUM_FORMS': '1000',
            'parents_list-0-id': str(rel.pk),
            'parents_list-0-inheriting_list': str(shared.pk),
            'parents_list-0-super_list': str(self.list_b.pk),
            'playlistentry_set-TOTAL_FORMS': '0',
            'playlistentry_set-INITIAL_FORMS': '0',
            'playlistentry_set-MIN_NUM_FORMS': '0',
            'playlistentry_set-MAX_NUM_FORMS': '1000',
            '_save': 'Save',
        })
        self.assertEqual(resp.status_code, 302, _errors(resp))
        rel.refresh_from_db()
        self.assertEqual(rel.super_list, self.list_b)

    def test_new_cross_team_parent_still_rejected(self):
        """Keeping an existing relation must not open the door to new ones."""
        own = Playlist.objects.create(name="ownList")
        own.teams.add(self.team_a)
        resp = self.client_a.post(f'/admin/screens/playlist/{own.pk}/change/', {
            'name': own.name,
            'description': '',
            'default_duration': '10',
            'interspersed_playlist': '',
            'interspersed_rate': '1',
            'parents_list-TOTAL_FORMS': '1',
            'parents_list-INITIAL_FORMS': '0',
            'parents_list-MIN_NUM_FORMS': '0',
            'parents_list-MAX_NUM_FORMS': '1000',
            'parents_list-0-inheriting_list': str(own.pk),
            'parents_list-0-super_list': str(self.list_b.pk),
            'playlistentry_set-TOTAL_FORMS': '0',
            'playlistentry_set-INITIAL_FORMS': '0',
            'playlistentry_set-MIN_NUM_FORMS': '0',
            'playlistentry_set-MAX_NUM_FORMS': '1000',
            '_save': 'Save',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PlaylistRelation.objects.filter(inheriting_list=own).count(), 0)

    # --- Source.playlists (declared multi-select; used to drop silently) -----

    def test_foreign_playlist_membership_is_not_silently_dropped(self):
        src = Source.objects.create(type=Source.IFRAME, name="srcShared", url="http://example.com/s")
        src.teams.add(self.team_a, self.team_b)
        src.playlists.set([self.list_a, self.list_b], through_defaults={"number": 10})

        resp = self.client_a.get(f'/admin/screens/source/{src.pk}/change/')
        html = resp.content.decode()
        self.assertIn("another team: Bravo", html)
        self.assertIn("belong to another team (Bravo)", html)

        resp = self.client_a.post(f'/admin/screens/source/{src.pk}/change/', {
            'type': str(src.type),
            'name': src.name,
            'url': src.url,
            'playlists': [str(self.list_a.pk), str(self.list_b.pk)],
            '_save': 'Save',
        })
        self.assertEqual(resp.status_code, 302, _errors(resp))
        self.assertEqual(
            set(src.playlists.values_list('pk', flat=True)),
            {self.list_a.pk, self.list_b.pk},
        )

    def test_source_playlist_picker_still_excludes_unrelated_other_team(self):
        src = Source.objects.create(type=Source.IFRAME, name="srcA", url="http://example.com/a")
        src.teams.add(self.team_a)
        resp = self.client_a.get(f'/admin/screens/source/{src.pk}/change/')
        self.assertNotContains(resp, "listBOther")

    def test_declared_playlists_field_is_not_mutated_across_requests(self):
        """The shared declared field must not carry one request's scope into the next."""
        from screens.forms import PlaylistAssigningSourceForm
        src = Source.objects.create(type=Source.IFRAME, name="srcShared", url="http://example.com/s")
        src.teams.add(self.team_a, self.team_b)
        src.playlists.set([self.list_b], through_defaults={"number": 10})
        self.client_a.get(f'/admin/screens/source/{src.pk}/change/')
        declared = PlaylistAssigningSourceForm.declared_fields['playlists']
        self.assertEqual(declared.foreign_labels, {})
        self.assertEqual(
            set(declared.queryset.values_list('pk', flat=True)),
            set(Playlist.objects.values_list('pk', flat=True)),
        )

    # --- Unaffected paths ----------------------------------------------------

    def test_superuser_sees_no_foreign_labels(self):
        sched = self._shared_schedule()
        c = Client()
        c.force_login(self.super)
        resp = c.get(f'/admin/screens/schedule/{sched.pk}/change/')
        self.assertNotContains(resp, "another team:")

    def test_multi_team_user_on_active_team_a_sees_the_label(self):
        """Scoping is by *active* team, so a member of both teams hits this too."""
        sched = self._shared_schedule()
        c = Client()
        c.force_login(self.user_ab)
        c.get('/admin/screens/schedule/')  # settle the active team (Alpha, first by name)
        resp = c.get(f'/admin/screens/schedule/{sched.pk}/change/')
        self.assertContains(resp, "another team: Bravo")
