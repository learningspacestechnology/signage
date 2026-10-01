"""Suggest estate records for the room_schedules display records.

Stdlib only. This is a suggestion aid on an admin page an operator confirms by
hand, not a search engine, so adding a fuzzy-matching dependency to
pyproject.toml is not a trade worth making.

Nothing here ever writes a link. Every suggestion is offered for confirmation,
never pre-selected, so a wrong guess cannot be accepted by reflex.
"""

import re
import unicodedata
from difflib import SequenceMatcher

#: Words that say what kind of space something is rather than which one. Dropped
#: before comparison, so "Lecture Theatre 2.14" and "LT 2.14" can meet.
NOISE = {
    'room', 'rm', 'the', 'building', 'bldg', 'block', 'level', 'floor',
    'lecture', 'theatre', 'theater', 'lt', 'seminar', 'teaching', 'tutorial',
    'meeting', 'lab', 'laboratory', 'studio', 'suite',
}

#: Below this, no suggestion is offered at all and the operator uses the full
#: list. Kept as a constant, and deliberately out of the help prose — the page
#: says "exact / strong / possible", never a percentage, so this stays a
#: tunable rather than a documented contract.
SUGGESTION_THRESHOLD = 0.65
STRONG_THRESHOLD = 0.85

#: How many suggestions a row offers. More than three and an operator stops
#: reading them and starts using the full list anyway.
SUGGESTIONS_SHOWN = 3


def normalise(text):
    """Casefold, strip accents and punctuation, drop noise words.

    >>> normalise("Appleton Tower — Lecture Theatre 2.14")
    'appleton tower 2 14'
    """
    text = unicodedata.normalize('NFKD', text or '')
    text = ''.join(c for c in text if not unicodedata.combining(c))
    text = text.casefold().replace('&', ' and ')
    text = re.sub(r'[^a-z0-9]+', ' ', text)
    return ' '.join(t for t in text.split() if t and t not in NOISE)


#: A floor/room number pair: "1.02", "2-14", "G/07". Not anchored to the start,
#: because it is usually the tail of a longer label.
ROOM_CODE_RE = re.compile(r'\b(\d{1,2}|[a-z])\s*[.\-/]\s*(\d{1,3}[a-z]?)\b')


def room_code(text):
    """The floor/room number in `text`, normalised, or None.

    >>> room_code("Seminar Room 1.02")
    '1.02'
    >>> room_code("Boardroom") is None
    True
    """
    match = ROOM_CODE_RE.search((text or '').casefold())
    return f"{match.group(1)}.{match.group(2)}" if match else None


def _ratio(a, b):
    return SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def score_building(display_name, candidate):
    """``(score, badge)`` for one estate building, or None below the threshold.

    The badge is what the page shows; it is a *word*, so the strength of a
    match is never conveyed by colour alone.

    There is no building code in the datastore feed, so unlike rooms there is
    no exact-identifier tier here — a building match is its name or nothing.
    """
    left, right = normalise(display_name), normalise(candidate.name)
    if left and left == right:
        return 1.0, "Exact name"
    ratio = _ratio(left, right)
    if ratio >= STRONG_THRESHOLD:
        return ratio, "Strong"
    if ratio >= SUGGESTION_THRESHOLD:
        return ratio, "Possible"
    return None


def score_room(display_name, candidate):
    """``(score, badge)`` for one estate room, or None below the threshold.

    Only ever called with candidates from the *linked building*. Room labels
    like "2.14" repeat across the estate, so scoring them globally would
    produce confident nonsense.
    """
    left, right = normalise(display_name), normalise(candidate.name)
    if left and left == right:
        return 1.0, "Exact name"
    left_code, right_code = room_code(display_name), room_code(candidate.name)
    if left_code and left_code == right_code:
        return 0.90, "Room number"
    ratio = _ratio(left, right)
    if ratio >= STRONG_THRESHOLD:
        return ratio, "Strong"
    if ratio >= SUGGESTION_THRESHOLD:
        return ratio, "Possible"
    return None


def _rank(display_name, candidates, scorer):
    scored = []
    for candidate in candidates:
        result = scorer(display_name, candidate)
        if result is not None:
            scored.append((result[0], candidate.name, candidate, result[1]))
    # Name as the tie-break, so the order does not depend on queryset ordering.
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [{'object': obj, 'badge': badge, 'score': score}
            for score, _, obj, badge in scored[:SUGGESTIONS_SHOWN]]


def suggest_buildings(display_name, candidates):
    return _rank(display_name, candidates, score_building)


def suggest_rooms(display_name, candidates):
    return _rank(display_name, candidates, score_room)
