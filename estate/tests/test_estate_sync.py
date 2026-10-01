"""Reconciliation of the Learning Spaces Datastore room feed into the mirror.

Payloads are built by hand rather than recorded, following
room_schedules/tests/test_o365_sync.py. `reconcile_estate` is a plain function
over a list of dicts, so most of this needs no patching at all.

The field names and the awkward values here are the live signage feed's own:
three campus columns that mean three different things, a short code in mixed
case, a Boolean `active`, and an Estates `building_code` per room.
"""

from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from estate.models import Building, Campus, Room
from estate.sync import building_key, reconcile_estate
from screens.models import Playlist, Schedule, Screen, Team


def room_row(lsd_id, *, campus="Central North", campus_short="CN",
             building="Appleton Tower", name=None, public_campus="Central",
             **extra):
    """One /v1/signage/rooms/ row, as the live feed shapes it.

    `campus` here is the internal campus_lst, which is the identity. The row's
    own `campus` key is the public grouping, set through `public_campus`.
    """
    row = {
        'id': lsd_id,
        'active': True,
        'campus': public_campus,
        'campus_name_short': campus_short,
        'campus_lst': campus,
        'building': building,
        'building_code': '0131',
        'name': name if name is not None else f"Room {lsd_id}",
        'capacity': 110,
        'optime_index': 543,
        'room_status': 'General Teaching',
        'voip_number': 505000,
        'support_type': 'Central',
        'service_provider': 'LST',
        'latitude': '55.946832',
        'longitude': '-3.187007',
        'address': '13-15 South College Street, Edinburgh, EH8 9AA',
    }
    row.update(extra)
    return row


def _screen_in(room):
    """A Screen pointing at `room`, with the team and schedule it requires."""
    playlist = Playlist.objects.create(name="P")
    screen = Screen.objects.create(
        name=f"Screen for {room.name}", ip="10.0.0.1", room=room,
        schedule=Schedule.objects.create(name="S", default_playlist=playlist),
    )
    screen.teams.add(Team.objects.create(name="Alpha"))
    return screen


class BuildingKeyTests(TestCase):
    databases = []

    def test_it_is_the_campus_and_the_name(self):
        self.assertEqual(
            building_key("Central North", "Appleton Tower"),
            "central north|appleton tower")

    def test_the_same_name_on_two_campuses_is_two_keys(self):
        """"Medical School" really does exist on two campuses in the feed."""
        self.assertNotEqual(
            building_key("Central South", "Medical School"),
            building_key("Central West", "Medical School"))

    def test_it_survives_a_name_too_long_to_store(self):
        a = building_key("Central", "A" * 400)
        b = building_key("Central", "A" * 399 + "B")
        self.assertLessEqual(len(a), 255)
        self.assertNotEqual(a, b)


class DerivationTests(TestCase):
    """Campuses and buildings are derived; the feed has no endpoint for either."""

    def test_a_payload_becomes_campuses_buildings_and_rooms(self):
        summary = reconcile_estate([
            room_row("r1"),
            room_row("r2"),
            room_row("r3", building="Informatics Forum"),
            room_row("r4", campus="King's Buildings", campus_short="KB",
                     building="JCMB"),
        ])

        self.assertEqual(summary['rooms'], 4)
        self.assertEqual(summary['buildings'], 3)
        self.assertEqual(summary['campuses'], 2)
        self.assertEqual(Room.objects.count(), 4)

    def test_campus_identity_is_the_internal_name_not_the_short_code(self):
        """The feed splits "Central" into North/South/West; that is the point."""
        reconcile_estate([
            room_row("r1", campus="Central North", campus_short="CN"),
            room_row("r2", campus="Central South", campus_short="CS"),
            room_row("r3", campus="Central West", campus_short="CW"),
        ])
        self.assertEqual(
            sorted(Campus.objects.values_list('name', flat=True)),
            ["Central North", "Central South", "Central West"])

    def test_the_same_building_name_on_two_campuses_stays_two_buildings(self):
        reconcile_estate([
            room_row("r1", campus="Central South", building="Medical School"),
            room_row("r2", campus="Central West", building="Medical School"),
        ])
        self.assertEqual(Building.objects.filter(name="Medical School").count(), 2)

    def test_a_row_with_no_campus_or_building_is_skipped_not_invented(self):
        summary = reconcile_estate([
            room_row("r1"),
            room_row("r2", campus="", building=""),
        ])
        self.assertEqual(summary['skipped'], 1)
        self.assertEqual(Room.objects.count(), 1)


class CampusCodeTests(TestCase):
    """campus_name_short is an attribute, not an identity. It is dirty."""

    def test_the_short_code_is_stored_alongside_the_name(self):
        reconcile_estate([room_row("r1", campus="Holyrood", campus_short="HR")])
        self.assertEqual(Campus.objects.get().code, "HR")

    def test_case_variants_resolve_to_one_campus_with_one_code(self):
        """The live feed carries both "CW" and "cw"."""
        reconcile_estate([
            room_row("r1", campus="Central West", campus_short="CW"),
            room_row("r2", campus="Central West", campus_short="CW"),
            room_row("r3", campus="Central West", campus_short="cw"),
        ])
        self.assertEqual(Campus.objects.count(), 1)
        self.assertEqual(Campus.objects.get().code, "CW")

    def test_rows_with_a_blank_code_do_not_erase_it(self):
        """Some rows arrive with no short code at all."""
        reconcile_estate([
            room_row("r1", campus="Central West", campus_short="CW"),
            room_row("r2", campus="Central West", campus_short=None),
        ])
        self.assertEqual(Campus.objects.get().code, "CW")

    def test_a_code_used_by_two_campuses_does_not_merge_them(self):
        """The older feed used "KB" for King's Buildings and a test campus."""
        summary = reconcile_estate([
            room_row("r1", campus="King's Buildings", campus_short="KB"),
            room_row("r2", campus="Testing Campus", campus_short="KB"),
        ])
        self.assertEqual(Campus.objects.count(), 2)
        self.assertEqual(summary['campus_code_conflicts'], 0)

    def test_conflicting_codes_for_one_campus_are_counted(self):
        summary = reconcile_estate([
            room_row("r1", campus="Central West", campus_short="CW"),
            room_row("r2", campus="Central West", campus_short="XX"),
        ])
        self.assertEqual(summary['campus_code_conflicts'], 1)


class DriftTests(TestCase):
    """What happens across runs when the datastore's own data moves."""

    def test_rerunning_the_same_payload_changes_nothing(self):
        payload = [room_row("r1"), room_row("r2", building="JCMB")]
        reconcile_estate(payload)
        before = (
            set(Room.objects.values_list('pk', flat=True)),
            set(Building.objects.values_list('pk', flat=True)),
            set(Campus.objects.values_list('pk', flat=True)),
        )

        summary = reconcile_estate(payload)

        self.assertEqual(summary['rooms_created'], 0)
        self.assertNotIn('rooms_deleted', summary)
        self.assertEqual(
            (set(Room.objects.values_list('pk', flat=True)),
             set(Building.objects.values_list('pk', flat=True)),
             set(Campus.objects.values_list('pk', flat=True))),
            before,
        )

    def test_a_renamed_room_keeps_its_row(self):
        """Rooms key on the datastore's own id, so a rename is just an update."""
        reconcile_estate([room_row("r1", name="LT2")])
        pk = Room.objects.get().pk

        reconcile_estate([room_row("r1", name="Lecture Theatre 2")])

        self.assertEqual(Room.objects.get().pk, pk)
        self.assertEqual(Room.objects.get().name, "Lecture Theatre 2")

    def test_a_renamed_building_becomes_a_new_one_but_the_rooms_survive(self):
        """There is no building code in this feed, so the name is the key.

        The consequence to be aware of: a rename churns the Building row. Every
        Screen keeps its room, because rooms key on their own id.
        """
        reconcile_estate([room_row("r1", building="Appleton Tower")])
        old_building = Building.objects.get().pk
        room_pk = Room.objects.get().pk

        reconcile_estate([room_row("r1", building="Appleton Tower (South)")])

        self.assertEqual(Room.objects.get().pk, room_pk)
        self.assertEqual(Building.objects.count(), 1)
        self.assertNotEqual(Building.objects.get().pk, old_building)

    def test_a_room_moving_between_buildings_is_repointed(self):
        reconcile_estate([room_row("r1", building="Appleton Tower")])
        room_pk = Room.objects.get().pk

        reconcile_estate([room_row("r1", building="Informatics Forum")])

        room = Room.objects.get()
        self.assertEqual(room.pk, room_pk)
        self.assertEqual(room.building.name, "Informatics Forum")


class ReconciliationTests(TestCase):
    """Delete what nothing depends on; flag what something does."""

    def test_a_vanished_room_nothing_points_at_is_deleted(self):
        reconcile_estate([room_row("r1"), room_row("r2")])
        summary = reconcile_estate([room_row("r1")])

        self.assertEqual(summary['rooms_deleted'], 1)
        self.assertEqual(list(Room.objects.values_list('lsd_id', flat=True)), ['r1'])

    def test_a_vanished_room_a_screen_points_at_is_flagged_not_deleted(self):
        reconcile_estate([room_row("r1"), room_row("r2")])
        room = Room.objects.get(lsd_id="r2")
        screen = _screen_in(room)

        summary = reconcile_estate([room_row("r1")])

        room.refresh_from_db()
        screen.refresh_from_db()
        self.assertTrue(room.missing_from_source)
        self.assertEqual(screen.room_id, room.pk)
        self.assertEqual(summary.get('rooms_deleted', 0), 0)
        self.assertEqual(summary['rooms_flagged'], 1)

    def test_a_returning_room_loses_its_missing_flag(self):
        reconcile_estate([room_row("r1"), room_row("r2")])
        Room.objects.filter(lsd_id="r2").update(missing_from_source=True)

        reconcile_estate([room_row("r1"), room_row("r2")])

        self.assertFalse(Room.objects.get(lsd_id="r2").missing_from_source)

    def test_an_emptied_building_and_campus_go_in_the_same_run(self):
        """Children before parents, or a building would linger a run."""
        reconcile_estate([
            room_row("r1"),
            room_row("r2", campus="King's Buildings", building="JCMB"),
        ])

        reconcile_estate([room_row("r1")])

        self.assertEqual(list(Building.objects.values_list('name', flat=True)),
                         ['Appleton Tower'])
        self.assertEqual(list(Campus.objects.values_list('name', flat=True)),
                         ['Central North'])

    def test_a_building_whose_room_was_kept_is_kept_too(self):
        reconcile_estate([
            room_row("r1"),
            room_row("r2", campus="King's Buildings", building="JCMB"),
        ])
        _screen_in(Room.objects.get(lsd_id="r2"))

        reconcile_estate([room_row("r1")])

        self.assertTrue(Building.objects.get(name="JCMB").missing_from_source)
        self.assertTrue(
            Campus.objects.get(name="King's Buildings").missing_from_source)


class SafetyValveTests(TestCase):
    """The second net, behind the client's check against the declared count."""

    @override_settings(LSD_SYNC_MIN_ROOMS=5)
    def test_below_the_minimum_it_updates_but_does_not_reconcile(self):
        with override_settings(LSD_SYNC_MIN_ROOMS=1):
            reconcile_estate([room_row(f"r{i}") for i in range(6)])

        summary = reconcile_estate([room_row("r1")])

        self.assertFalse(summary['reconciled'])
        self.assertEqual(summary['reason'], 'below_min_rooms')
        self.assertEqual(Room.objects.count(), 6)
        self.assertFalse(Room.objects.filter(missing_from_source=True).exists())

    @override_settings(LSD_SYNC_MAX_SHRINK_PCT=50)
    def test_a_sudden_shrink_updates_but_does_not_reconcile(self):
        reconcile_estate([room_row(f"r{i}") for i in range(10)])

        summary = reconcile_estate([room_row("r1"), room_row("r2")])

        self.assertFalse(summary['reconciled'])
        self.assertEqual(summary['reason'], 'shrink_guard')
        self.assertEqual(Room.objects.count(), 10)

    @override_settings(LSD_SYNC_MAX_SHRINK_PCT=50)
    def test_a_shrink_inside_the_tolerance_still_reconciles(self):
        reconcile_estate([room_row(f"r{i}") for i in range(10)])

        summary = reconcile_estate([room_row(f"r{i}") for i in range(6)])

        self.assertTrue(summary['reconciled'])
        self.assertEqual(Room.objects.count(), 6)


class FieldMappingTests(TestCase):
    def test_the_stored_room_matches_the_feed_row(self):
        reconcile_estate([room_row("r1")])
        room = Room.objects.get()

        self.assertEqual(room.name, "Room r1")
        self.assertEqual(room.room_status, "General Teaching")
        self.assertEqual(room.capacity, 110)
        self.assertTrue(room.active)
        self.assertEqual(room.building_code, "0131")
        self.assertEqual(room.optime_index, 543)
        self.assertEqual(room.public_campus, "Central")
        self.assertEqual(room.support_type, "Central")
        self.assertEqual(room.service_provider, "LST")
        self.assertEqual(room.voip_number, 505000)
        self.assertEqual(str(room.latitude), "55.946832")
        self.assertEqual(room.campus.name, "Central North")
        self.assertTrue(room.has_support_contact)

    def test_the_public_campus_is_not_the_campus(self):
        """`campus` in the feed is a coarser grouping; campus_lst is identity."""
        reconcile_estate([
            room_row("r1", campus="Central West", public_campus="Lauriston"),
            room_row("r2", campus="Central West", public_campus="Central"),
            room_row("r3", campus="Central West", public_campus=None),
        ])
        self.assertEqual(Campus.objects.get().name, "Central West")
        self.assertEqual(
            sorted(Room.objects.values_list('public_campus', flat=True)),
            ["", "Central", "Lauriston"])

    def test_the_literal_string_None_is_treated_as_blank(self):
        """The old feed sent "None"; the fold stays as a cheap defence."""
        reconcile_estate([room_row(
            "r1", service_provider='None', room_status='None',
            voip_number=None)])
        room = Room.objects.get()
        self.assertEqual(room.service_provider, "")
        self.assertEqual(room.room_status, "")
        self.assertFalse(room.has_support_contact)

    def test_only_an_explicit_false_makes_a_room_inactive(self):
        """Malformed data fails towards no flag, not towards false alarms."""
        reconcile_estate([
            room_row("r1", active=True),
            room_row("r2", active=False),
            room_row("r3", active=None),
            room_row("r4", active="False"),
        ])
        self.assertEqual(
            list(Room.objects.filter(active=False)
                 .values_list('lsd_id', flat=True)),
            ["r2"])
        # Every row is imported regardless of what `active` says.
        self.assertEqual(Room.objects.count(), 4)

    def test_a_room_closing_upstream_is_marked_inactive_next_run(self):
        reconcile_estate([room_row("r1")])
        reconcile_estate([room_row("r1", active=False)])
        self.assertFalse(Room.objects.get().active)

    def test_an_address_differing_only_in_line_endings_is_stored_one_way(self):
        reconcile_estate([
            room_row("r1", address="47 Potterow\r\nEdinburgh\r\nEH8 9BT"),
            room_row("r2", address="47 Potterow\nEdinburgh\nEH8 9BT"),
        ])
        self.assertEqual(
            Room.objects.values_list('address', flat=True).distinct().count(), 1)

    def test_building_code_is_kept_per_room_not_used_as_a_key(self):
        """One of our buildings can span several Estates codes, and vice versa.

        IGMM carries three codes; 0228 covers two of our building names.
        Neither may split or merge a Building.
        """
        reconcile_estate([
            room_row("r1", building="IGMM", building_code="2318"),
            room_row("r2", building="IGMM", building_code="2302"),
            room_row("r2b", building="IGMM", building_code="2302",
                     name="A differently named room"),
            room_row("r3", building="40 George Sq", building_code="0228"),
            room_row("r4", building="40 George Sq Lower Hub",
                     building_code="0228"),
            room_row("r5", building="Guest House", building_code=None),
        ])
        self.assertEqual(Building.objects.count(), 4)
        self.assertEqual(
            Building.objects.get(name="IGMM").estates_codes, ["2302", "2318"])
        self.assertEqual(Building.objects.get(name="Guest House").estates_codes, [])
        self.assertEqual(
            Room.objects.filter(building_code="0228").values('building')
            .distinct().count(), 2)

    def test_a_malformed_row_does_not_abort_the_run(self):
        reconcile_estate([
            room_row("r1", capacity="lots", latitude="north",
                     voip_number="n/a", optime_index="x"),
            room_row("r2"),
        ])
        self.assertEqual(Room.objects.count(), 2)
        odd = Room.objects.get(lsd_id="r1")
        self.assertIsNone(odd.capacity)
        self.assertIsNone(odd.latitude)
        self.assertIsNone(odd.voip_number)
        self.assertIsNone(odd.optime_index)

    def test_sparse_rows_are_fine(self):
        """Most columns are null on most rooms in the live feed."""
        reconcile_estate([{
            'id': 'r1', 'campus_lst': 'Holyrood', 'building': 'Old College',
            'name': 'Room 1',
        }])
        room = Room.objects.get()
        self.assertEqual(room.name, "Room 1")
        self.assertIsNone(room.capacity)
        self.assertTrue(room.active)
        self.assertEqual(room.building_code, "")
        self.assertEqual(room.campus.code, "")

    def test_an_unnamed_room_falls_back_to_its_id(self):
        reconcile_estate([room_row("r1", name="")])
        self.assertEqual(Room.objects.get().name, "r1")

    def test_the_fields_this_feed_does_not_carry_are_not_modelled(self):
        """Dropped with the move to the signage feed, or never in it.

        A column the sync can no longer fill would keep its last value for
        ever and look current.
        """
        stored = {f.name for f in Room._meta.get_fields()}
        for gone in ('usage', 'av_type', 'support_group', 'host_key',
                     'active_raw', 'bookable', 'map_slug', 'org',
                     'owner_label', 'usages', 'room_type', 'av_type_slug'):
            self.assertNotIn(gone, stored, gone)


class TaskTests(TestCase):
    """The Celery wrapper, patched at its import site."""

    def test_the_task_fetches_then_reconciles_and_returns_the_summary(self):
        from estate.tasks import sync_estate

        with patch("estate.tasks.fetch_rooms", return_value=[room_row("r1")]):
            summary = sync_estate()

        self.assertEqual(summary['rooms'], 1)
        self.assertTrue(summary['reconciled'])
        self.assertEqual(Room.objects.count(), 1)

    def test_a_fetch_failure_leaves_the_mirror_untouched(self):
        from estate.tasks import sync_estate

        reconcile_estate([room_row("r1")])
        with patch("estate.tasks.fetch_rooms",
                   side_effect=RuntimeError("LSD API error 503")):
            with self.assertRaises(RuntimeError):
                sync_estate()

        self.assertEqual(Room.objects.count(), 1)
        self.assertFalse(Room.objects.get().missing_from_source)


class RunTimestampTests(TestCase):
    def test_rows_seen_this_run_carry_the_run_timestamp(self):
        started = timezone.now()
        reconcile_estate([room_row("r1")], run_started=started)
        self.assertEqual(Room.objects.get().last_seen_at, started)
        self.assertEqual(Building.objects.get().last_seen_at, started)
        self.assertEqual(Campus.objects.get().last_seen_at, started)
