from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.template.loader import get_template
from django.urls import reverse
from datetime import timedelta
from django.db.models import Case, CharField, OuterRef, Q, Subquery, Value, When
from django.utils import timezone

from screens.models.schedule import Schedule


TICKER_LAYOUT_OVERLAY = "OVERLAY"
TICKER_LAYOUT_SHRINK = "SHRINK"
TICKER_LAYOUT_CHOICES = [
    (TICKER_LAYOUT_OVERLAY, "Overlay (cover bottom of content)"),
    (TICKER_LAYOUT_SHRINK, "Shrink content to fit above ticker"),
]

TICKER_STYLE_CLASSIC = "CLASSIC"
TICKER_STYLE_MINIMAL = "MINIMAL"
TICKER_STYLE_BOLD = "BOLD"
TICKER_STYLE_PRESETS = [
    (TICKER_STYLE_CLASSIC, "Classic news ticker"),
    (TICKER_STYLE_MINIMAL, "Minimal subtle bar"),
    (TICKER_STYLE_BOLD, "Bold marquee"),
]

# How recently a screen must have checked in to still count as online. Mirrored
# in the help docs as SCREEN_OFFLINE_AFTER ("one minute") — change both together.
ONLINE_WINDOW = timedelta(minutes=1)

# A screen that stopped checking in this recently is amber rather than red: one
# missed poll is usually a blip, not a dead device. Mirrored in the help docs as
# SCREEN_ATTENTION_AFTER.
ATTENTION_WINDOW = timedelta(minutes=10)

# How long a successful ping keeps a screen amber. Deliberately longer than the
# probe cadence (5 minutes, see CELERY_BEAT_SCHEDULE) so that one missed probe
# does not flip a reachable screen to red. Mirrored as SCREEN_PING_WINDOW.
PING_WINDOW = timedelta(minutes=15)


class ScreenStatus(models.TextChoices):
    """What the system currently believes about a screen.

    Three states rather than two because the two signals we have answer
    different questions. `last_seen` says "the player is polling"; a successful
    ping says "the box is powered and on the network". ATTENTION is the gap
    between them, and it is the diagnostically useful one: the device is alive
    but its software is not doing its job.
    """

    ONLINE = "online", "Online"
    ATTENTION = "attention", "Needs attention"
    OFFLINE = "offline", "Offline"


class StatusReason(models.TextChoices):
    """Why a screen is in the state it is in.

    ATTENTION has two causes and they call for different actions, so the reason
    is carried alongside the status rather than being inferred at the point of
    display. Labels are written to be read by an operator as-is.
    """

    PING_ONLY = "ping_only", "Responds to ping but is not reporting"
    RECENTLY_LOST = "recently_lost", "Stopped reporting recently"
    NO_RESPONSE = "no_response", "No contact and no ping response"
    NO_CONTACT = "no_contact", "No contact"

#: Sort order for the status column: healthiest first ascending, worst first
#: descending. Explicit because the raw values happen to sort "attention",
#: "offline", "online" alphabetically, which is meaningless as a severity order.
STATUS_RANK = {
    ScreenStatus.ONLINE: 0,
    ScreenStatus.ATTENTION: 1,
    ScreenStatus.OFFLINE: 2,
}


class ScreenQuerySet(models.QuerySet):
    def with_status(self):
        """Annotate the derived status, its reason, and a sortable rank.

        Named `derived_*` rather than `status`/`status_reason` on purpose: an
        annotation silently shadows a same-named method on the instances it
        returns, so `screen.status` would be a string on annotated rows and a
        bound method everywhere else.

        Also annotates the *recorded* status from the latest ScreenStatusEvent.
        That is only as fresh as the last check_screens run, so it is never the
        display authority — see Screen.status_since_display().
        """
        from screens.models.screen_status_event import ScreenStatusEvent

        tiers = Screen._status_tiers()
        latest = (ScreenStatusEvent.objects
                  .filter(screen=OuterRef("pk"))
                  .order_by("-at", "-pk"))

        return self.annotate(
            derived_status=Case(
                *[When(q, then=Value(str(status))) for status, _reason, q, _pred in tiers],
                default=Value(str(ScreenStatus.OFFLINE)),
                output_field=CharField(),
            ),
            derived_reason=Case(
                *[When(q, then=Value(str(reason))) for _status, reason, q, _pred in tiers],
                default=Value(str(StatusReason.NO_CONTACT)),
                output_field=CharField(),
            ),
            status_rank=Case(
                *[When(q, then=Value(STATUS_RANK[status]))
                  for status, _reason, q, _pred in tiers],
                default=Value(STATUS_RANK[ScreenStatus.OFFLINE]),
                output_field=models.IntegerField(),
            ),
            recorded_status=Subquery(latest.values("status")[:1]),
            recorded_reason=Subquery(latest.values("reason")[:1]),
            status_since=Subquery(latest.values("at")[:1]),
        )

    def needing_attention(self):
        """Screens that are not online: amber first, then longest-unseen first.

        Amber before red is deliberate. A screen that has been dark for three
        days is a known quantity; one that answers ping but stopped reporting
        is a new, usually fixable fault, and is what an operator should look at
        first.
        """
        return (self.with_status()
                .exclude(derived_status=str(ScreenStatus.ONLINE))
                .order_by("status_rank", "last_seen"))


TICKER_PRESET_VALUES = {
    TICKER_STYLE_CLASSIC: {"font_size": 50, "font_color": "#ffffff", "bg_color": "#000000",
                           "bg_opacity": 100, "scroll_speed": 80, "bar_height_vh": 6},
    TICKER_STYLE_MINIMAL: {"font_size": 32, "font_color": "#ffffff", "bg_color": "#222222",
                           "bg_opacity": 70, "scroll_speed": 50, "bar_height_vh": 4},
    TICKER_STYLE_BOLD: {"font_size": 70, "font_color": "#ffffff", "bg_color": "#000000",
                        "bg_opacity": 100, "scroll_speed": 120, "bar_height_vh": 10},
}


class Screen(models.Model):
    objects = ScreenQuerySet.as_manager()

    name = models.TextField()
    schedule = models.ForeignKey(Schedule, on_delete=models.PROTECT, null=True,
                                 help_text="The schedule that decides which playlist this screen shows at any given date and time.")
    interspersed_playlist = models.ForeignKey("Playlist",
                                              null=True,
                                              default=None,
                                              on_delete=models.SET_NULL,
                                              blank=True,
                                              related_name="interspersed_into_screens",
                                              verbose_name="Interspersed playlist",
                                              help_text="A playlist mixed into whatever this screen is showing, "
                                                        "whichever playlist that is (e.g. an event schedule or room "
                                                        "sign). Leave blank for none.")
    interspersed_rate = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        verbose_name="Interspersed rate",
        help_text="How many items play before one interspersed item. "
                  "1 shows an interspersed item after every entry.",
    )
    ip = models.GenericIPAddressField(
        help_text="The device's network address (IPv4 or IPv6). The system uses it to recognise this physical screen.")
    last_seen = models.DateTimeField(auto_now_add=True, blank=True)
    # The screen's half of the publish signal, matching Playlist.last_updated.
    # aggregate_last_updated() in screens/views.py maxes over both, so a change
    # here reaches devices even when no playlist row moved -- e.g. pointing the
    # screen at an *older* interspersed playlist, or changing only the rate,
    # neither of which a max() over playlist timestamps can see.
    #
    # auto_now means *any* full save() republishes: renaming a screen or fixing
    # its IP restarts every attached device's rotation from item one. Accepted
    # -- a couple of seconds, and rare.
    #
    # The 60-second heartbeat is the write that must not move it, and is kept
    # off by _get_meta saving with update_fields=["last_seen"]:
    # Model._save_table filters the field list by update_fields *before*
    # calling field.pre_save(), so auto_now never fires for a field left out.
    # Do not turn that into a plain save(), and do not add a post_save receiver
    # here without remembering it fires once per device per minute.
    last_updated = models.DateTimeField(auto_now=True)
    # Reachability, the outbound half of the status picture. Written only by
    # screens.tasks.check_screens, and only ever through a queryset .update()
    # so that last_updated's auto_now above cannot fire -- see the note there.
    #
    # Both null while probing is off (the default), which makes the ping tier
    # unmatchable and reduces status to the heartbeat alone. Keeping _attempt
    # separate from _ok is what distinguishes "probed, no answer" from "never
    # probed", and those mean very different things to whoever is reading.
    last_ping_ok = models.DateTimeField(null=True, blank=True, editable=False)
    last_ping_attempt = models.DateTimeField(null=True, blank=True, editable=False)
    teams = models.ManyToManyField("screens.Team", related_name="screens")

    # Editable by anyone with the change_ticker_settings permission
    ticker_enabled = models.BooleanField(default=False)
    ticker_layout = models.CharField(max_length=10, choices=TICKER_LAYOUT_CHOICES, default=TICKER_LAYOUT_OVERLAY,
                                     help_text="Overlay draws the ticker on top of the content. "
                                               "Shrink scales the content down to make room for the ticker below it.")

    # Editable by anyone with the change_ticker_text permission
    ticker_text = models.TextField(blank=True, default="")
    ticker_style_preset = models.CharField(max_length=10, choices=TICKER_STYLE_PRESETS, default=TICKER_STYLE_CLASSIC,
                                           help_text="Visual preset for the ticker. Individual colors, sizes and speed "
                                                     "can be overridden by the fields below.")
    ticker_font_size_px = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Override preset font size (px). Leave blank to use preset.",
    )
    ticker_font_color = models.CharField(
        max_length=32, blank=True, default="",
        help_text="CSS color (e.g. #ffffff). Leave blank to use preset.",
    )
    ticker_background_color = models.CharField(
        max_length=32, blank=True, default="",
        help_text="CSS color. Leave blank to use preset.",
    )
    ticker_background_opacity = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MaxValueValidator(100)],
        help_text=("Background opacity 0-100 (%). Leave blank to use preset. "
                   "Text stays fully opaque regardless."),
    )
    ticker_scroll_speed_px_sec = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Override preset scroll speed (px/sec). Leave blank to use preset.",
    )

    class Meta:
        permissions = [
            ("change_ticker_text", "Can change ticker text and style on screens"),
            ("change_ticker_settings", "Can turn the ticker on and choose its layout on screens"),
        ]

    def clean(self):
        super().clean()
        if self.pk and not self.teams.exists():
            raise ValidationError("Screen must belong to at least one team.")

    def has_ticker(self):
        return self.ticker_enabled and bool(self.ticker_text.strip())

    def resolved_ticker_style(self):
        base = dict(TICKER_PRESET_VALUES[self.ticker_style_preset])
        if self.ticker_font_size_px:
            base["font_size"] = self.ticker_font_size_px
        if self.ticker_font_color:
            base["font_color"] = self.ticker_font_color
        if self.ticker_background_color:
            base["bg_color"] = self.ticker_background_color
        if self.ticker_background_opacity is not None:
            base["bg_opacity"] = self.ticker_background_opacity
        if self.ticker_scroll_speed_px_sec:
            base["scroll_speed"] = self.ticker_scroll_speed_px_sec
        return base
    
    @staticmethod
    def online_cutoff():
        """The `last_seen` threshold for counting as online.

        Shared with the admin's online filter so the tick in the list and the
        filter that hides it can never disagree. Deliberately a value rather
        than a queryset: the answer moves with the clock, so it has to be
        recomputed per request rather than captured at import.
        """
        return timezone.now() - ONLINE_WINDOW

    @classmethod
    def _status_tiers(cls):
        """Ordered (status, reason, Q, python predicate). First match wins.

        The single source of truth for both Screen.status() and the
        ScreenQuerySet.with_status() annotation: defining the tiers once as
        data is what stops the badge, the changelist filter and the dashboard
        doughnut from drifting apart, the same way online_cutoff() is shared
        with the filter today.

        All three cutoffs come off one `now`, and are built per call rather
        than captured at import, because the answer moves with the clock.

        Order matters. Ping beats grace: a screen that answers ping *and*
        stopped reporting four minutes ago is amber for the more informative
        of the two reasons. Anything that matches no tier is OFFLINE, with the
        reason depending on whether a probe was actually attempted.
        """
        now = timezone.now()
        return (
            (ScreenStatus.ONLINE, "",
             Q(last_seen__gte=now - ONLINE_WINDOW),
             lambda s: s.last_seen is not None and s.last_seen >= now - ONLINE_WINDOW),
            (ScreenStatus.ATTENTION, StatusReason.PING_ONLY,
             Q(last_ping_ok__gte=now - PING_WINDOW),
             lambda s: s.last_ping_ok is not None and s.last_ping_ok >= now - PING_WINDOW),
            (ScreenStatus.ATTENTION, StatusReason.RECENTLY_LOST,
             Q(last_seen__gte=now - ATTENTION_WINDOW),
             lambda s: s.last_seen is not None and s.last_seen >= now - ATTENTION_WINDOW),
            (ScreenStatus.OFFLINE, StatusReason.NO_RESPONSE,
             Q(last_ping_attempt__isnull=False),
             lambda s: s.last_ping_attempt is not None),
        )

    def status_and_reason(self):
        """This screen's derived (status, reason), as a pair.

        One method rather than two so a caller wanting both walks the tiers
        once. Both are recomputed on every call -- there is no stored status;
        ScreenStatusEvent records transitions but never answers "what is it
        now".
        """
        for status, reason, _q, matches in Screen._status_tiers():
            if matches(self):
                return status, reason
        return ScreenStatus.OFFLINE, StatusReason.NO_CONTACT

    def status(self):
        return self.status_and_reason()[0]

    def status_label(self):
        return ScreenStatus(self.status()).label

    def status_reason_label(self):
        reason = self.status_and_reason()[1]
        return StatusReason(reason).label if reason else ""

    def online(self):
        return self.status() == ScreenStatus.ONLINE
    online.boolean = True

    def screen_preview(self):
        if self.id:
            return get_template("screens/screen_preview.html").render({"screen_url": self.get_absolute_url()})

    screen_preview.short_description = 'Preview'
        

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('screens/screen_view', args=[str(self.id)])
