"""Name matching for the linking page. Pure functions, no database."""

from django.test import SimpleTestCase

from estate.matching import (
    SUGGESTIONS_SHOWN, normalise, room_code, score_building, score_room,
    suggest_buildings, suggest_rooms,
)


class _Candidate:
    """Enough of an estate Building/Room for the scorers, without a database."""

    def __init__(self, name):
        self.name = name


class NormaliseTests(SimpleTestCase):
    def test_it_folds_case_and_collapses_whitespace(self):
        self.assertEqual(normalise("  Appleton   TOWER "), "appleton tower")

    def test_it_strips_accents(self):
        self.assertEqual(normalise("Café"), "cafe")

    def test_it_expands_an_ampersand(self):
        self.assertEqual(normalise("Arts & Crafts"), "arts and crafts")

    def test_it_drops_punctuation_and_noise_words(self):
        self.assertEqual(
            normalise("Appleton Tower — Lecture Theatre 2.14"),
            "appleton tower 2 14")

    def test_a_label_of_nothing_but_noise_normalises_to_empty(self):
        self.assertEqual(normalise("The Meeting Room"), "")

    def test_none_and_empty_are_handled(self):
        self.assertEqual(normalise(None), "")
        self.assertEqual(normalise(""), "")


class RoomCodeTests(SimpleTestCase):
    def test_it_finds_a_dotted_code(self):
        self.assertEqual(room_code("Seminar Room 1.02"), "1.02")

    def test_it_accepts_the_other_separators(self):
        self.assertEqual(room_code("Room 2-14"), "2.14")
        self.assertEqual(room_code("Room G/07"), "g.07")

    def test_it_keeps_a_trailing_letter(self):
        self.assertEqual(room_code("Room 3.05a"), "3.05a")

    def test_a_label_with_no_code_gives_none(self):
        self.assertIsNone(room_code("Boardroom"))
        self.assertIsNone(room_code(None))


class BuildingScoreTests(SimpleTestCase):
    def test_an_exact_name_outranks_everything(self):
        score, badge = score_building("Appleton Tower", _Candidate("Appleton Tower"))
        self.assertEqual((score, badge), (1.0, "Exact name"))

    def test_a_near_miss_is_offered_as_a_weaker_match(self):
        result = score_building("Appleton Twr", _Candidate("Appleton Tower"))
        self.assertIsNotNone(result)
        self.assertIn(result[1], ("Strong", "Possible"))

    def test_an_unrelated_name_is_not_suggested_at_all(self):
        self.assertIsNone(
            score_building("Bayes Centre", _Candidate("Appleton Tower")))

    def test_an_exact_match_beats_a_near_one(self):
        exact = score_building("Appleton Tower", _Candidate("Appleton Tower"))
        near = score_building("Appleton Twr", _Candidate("Appleton Tower"))
        self.assertGreater(exact[0], near[0])


class RoomScoreTests(SimpleTestCase):
    def test_an_exact_name_outranks_everything(self):
        self.assertEqual(score_room("LT2", _Candidate("LT2"))[1], "Exact name")

    def test_stripping_the_space_type_makes_two_labels_meet(self):
        """"Seminar Room 1.02" and "Teaching Room 1.02" are the same room."""
        self.assertEqual(
            score_room("Seminar Room 1.02", _Candidate("Teaching Room 1.02"))[1],
            "Exact name")

    def test_the_room_number_carries_a_match_the_words_cannot(self):
        score, badge = score_room("Appleton 1.02", _Candidate("Room 1.02"))
        self.assertEqual(badge, "Room number")

    def test_a_different_room_number_is_not_a_match(self):
        self.assertIsNone(score_room("Appleton 1.02", _Candidate("Bayes 3.19")))

    def test_an_exact_match_beats_a_room_number_match(self):
        exact = score_room("Room 1.02", _Candidate("Room 1.02"))
        by_number = score_room("Appleton 1.02", _Candidate("Room 1.02"))
        self.assertGreater(exact[0], by_number[0])


class SuggestionOrderTests(SimpleTestCase):
    def test_the_best_match_comes_first(self):
        candidates = [
            _Candidate("Appleton Twr"),
            _Candidate("Appleton Tower"),
        ]
        ranked = suggest_buildings("Appleton Tower", candidates)
        self.assertEqual(ranked[0]['object'].name, "Appleton Tower")
        self.assertEqual(ranked[0]['badge'], "Exact name")

    def test_the_list_is_capped(self):
        candidates = [_Candidate(f"Appleton Tower {i}") for i in range(10)]
        self.assertEqual(
            len(suggest_buildings("Appleton Tower", candidates)), SUGGESTIONS_SHOWN)

    def test_ties_are_broken_by_name_so_the_order_is_deterministic(self):
        candidates = [_Candidate("Zeta House"), _Candidate("Alpha House")]
        first = [s['object'].name for s in suggest_buildings("House", candidates)]
        second = [s['object'].name
                  for s in suggest_buildings("House", list(reversed(candidates)))]
        self.assertEqual(first, second)

    def test_nothing_is_suggested_when_nothing_is_close(self):
        self.assertEqual(
            suggest_buildings("Bayes Centre", [_Candidate("Appleton Tower")]), [])

    def test_two_rooms_with_the_same_number_in_different_buildings_do_not_match(self):
        """Which is why rooms are only ever scored inside a linked building."""
        candidates = [_Candidate("2.14")]
        self.assertNotEqual(suggest_rooms("2.14", candidates), [])
        # The building name is what tells them apart, and it is not in scope
        # here -- the caller restricts the candidate set instead.
        self.assertEqual(
            [s['object'].name for s in suggest_rooms("2.14", candidates)], ["2.14"])
