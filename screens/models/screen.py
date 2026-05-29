from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.db import models
from django.template.loader import get_template
from django.urls import reverse
from datetime import timedelta
from django.db.models import Q
from django.utils import timezone

from screens.models import Source
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

TICKER_PRESET_VALUES = {
    TICKER_STYLE_CLASSIC: {"font_size": 50, "font_color": "#ffffff", "bg_color": "#000000",
                           "bg_opacity": 100, "scroll_speed": 80, "bar_height_vh": 6},
    TICKER_STYLE_MINIMAL: {"font_size": 32, "font_color": "#ffffff", "bg_color": "#222222",
                           "bg_opacity": 70, "scroll_speed": 50, "bar_height_vh": 4},
    TICKER_STYLE_BOLD: {"font_size": 70, "font_color": "#ffffff", "bg_color": "#000000",
                        "bg_opacity": 100, "scroll_speed": 120, "bar_height_vh": 10},
}


class Screen(models.Model):
    name = models.TextField()
    schedule = models.ForeignKey(Schedule, on_delete=models.PROTECT, null=True)
    interspersed_source = models.ForeignKey(Source,
                                            null=True,
                                            default=None,
                                            on_delete=models.SET_NULL,
                                            blank=True,
                                            help_text="Optional (you probably want an event schedule here)")
    ip = models.GenericIPAddressField()
    last_seen = models.DateTimeField(auto_now_add=True, blank=True)
    teams = models.ManyToManyField("screens.Team", related_name="screens")

    # Superuser-only ticker gates
    ticker_enabled = models.BooleanField(default=False)
    ticker_layout = models.CharField(max_length=10, choices=TICKER_LAYOUT_CHOICES, default=TICKER_LAYOUT_OVERLAY)

    # Editable by anyone with the change_ticker_text permission
    ticker_text = models.TextField(blank=True, default="")
    ticker_style_preset = models.CharField(max_length=10, choices=TICKER_STYLE_PRESETS, default=TICKER_STYLE_CLASSIC)
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
        permissions = [("change_ticker_text", "Can change ticker text and style on screens")]

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
    
    def online(self):
        return self.last_seen and self.last_seen >= timezone.now()-timedelta(minutes=1)
    online.boolean = True

    def screen_preview(self):
        if self.id:
            return get_template("screens/screen_preview.html").render({"screen_url": self.get_absolute_url()})

    screen_preview.short_description = 'Preview'
        

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('screens/screen_view', args=[str(self.id)])
