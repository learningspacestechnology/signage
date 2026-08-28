"""Tests for the per-user admin accent colour picker.

The contrast test is the load-bearing one: it is what actually backs the
accessibility claim, and it makes every hex in `screens/accents.py`
machine-checked rather than trusted. The rest cover the write path and the
couplings to django-unfold that an upgrade could break silently.
"""
from pathlib import Path

import unfold
from django.contrib.auth.models import Permission, User
from django.contrib.contenttypes.models import ContentType
from django.test import Client, TestCase

from advertising.admin import accent_palette, accent_picker_items, accent_slug
from screens.accents import ACCENTS, DARK_WEIGHTS, DEFAULT_ACCENT, WEIGHTS
from screens.models import Source, Team, UserPreference

#: Backgrounds the admin actually paints behind primary-coloured text.
LIGHT_BG = "#ffffff"
DARK_BG = "#18181b"  # bg-base-900

AA = 4.5

CSS_DIR = Path(__file__).resolve().parent.parent / "static" / "screens" / "css" / "accent"
UNFOLD_TEMPLATES = Path(unfold.__file__).resolve().parent / "templates" / "unfold"


def _rgb(value):
    value = value.lstrip("#")
    return [int(value[i:i + 2], 16) for i in (0, 2, 4)]


def _luminance(value):
    def channel(raw):
        c = raw / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in _rgb(value))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b):
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def _css_colour(value):
    """How Unfold renders a hex into the page (`unfold.utils.convert_color`)."""
    return "rgb({}, {}, {})".format(*_rgb(value))


class AccentPaletteTests(TestCase):
    """The palettes themselves — no HTTP involved."""

    # --- Contrast ---

    def test_every_palette_meets_aa_in_light_mode(self):
        """500/600/700 carry text on white, and 600 carries white text."""
        for slug, palette in ACCENTS.items():
            light = palette["light"]
            for weight in ("500", "600", "700"):
                with self.subTest(accent=slug, weight=weight, mode="light"):
                    ratio = _contrast(light[weight], LIGHT_BG)
                    self.assertGreaterEqual(
                        ratio, AA,
                        f"{slug} light {weight} ({light[weight]}) is {ratio:.2f}:1 "
                        f"on white, below WCAG AA {AA}:1",
                    )
            with self.subTest(accent=slug, check="white-on-600"):
                ratio = _contrast(LIGHT_BG, light["600"])
                self.assertGreaterEqual(ratio, AA, f"{slug}: {ratio:.2f}:1")

    def test_every_palette_meets_aa_in_dark_mode(self):
        """The whole reason for a second ramp — see screens/accents.py."""
        for slug, palette in ACCENTS.items():
            for weight in DARK_WEIGHTS:
                with self.subTest(accent=slug, weight=weight, mode="dark"):
                    value = palette["dark"][weight]
                    ratio = _contrast(value, DARK_BG)
                    self.assertGreaterEqual(
                        ratio, AA,
                        f"{slug} dark {weight} ({value}) is {ratio:.2f}:1 on "
                        f"{DARK_BG}, below WCAG AA {AA}:1",
                    )

    def test_unfold_stock_purple_would_fail(self):
        """Guards the premise. If this ever passes, the two-ramp scheme may be
        unnecessary — but check *why* before deleting anything."""
        stock = "#ad46ff"  # unfold's default primary-500
        self.assertLess(_contrast(stock, LIGHT_BG), AA)
        self.assertLess(_contrast(stock, DARK_BG), AA)

    # --- Registry shape ---

    def test_every_palette_defines_a_complete_ramp(self):
        for slug, palette in ACCENTS.items():
            with self.subTest(accent=slug):
                self.assertEqual(tuple(palette["light"]), WEIGHTS)
                self.assertEqual(tuple(palette["dark"]), DARK_WEIGHTS)
                self.assertTrue(palette["label"])

    def test_ramps_darken_monotonically(self):
        """A non-monotonic ramp still passes the contrast checks but looks wrong
        wherever Unfold uses two weights together (hover, borders)."""
        for slug, palette in ACCENTS.items():
            light = palette["light"]
            for lighter, darker in zip(WEIGHTS, WEIGHTS[1:]):
                with self.subTest(accent=slug, pair=(lighter, darker)):
                    self.assertGreater(
                        _luminance(light[lighter]), _luminance(light[darker]),
                        f"{slug}: {lighter} is not lighter than {darker}",
                    )

    def test_default_accent_is_registered(self):
        self.assertIn(DEFAULT_ACCENT, ACCENTS)

    # --- Generated stylesheets ---

    def test_each_palette_has_a_matching_dark_stylesheet(self):
        """The CSS files are generated from ACCENTS; this catches an edit to one
        without the other. To regenerate after changing a palette:

            uv run python -c "
            from pathlib import Path
            from screens.accents import ACCENTS, DARK_WEIGHTS
            ...  # see git history of this file's sibling CSS for the header
            "
        """
        for slug, palette in ACCENTS.items():
            with self.subTest(accent=slug):
                path = CSS_DIR / f"{slug}.css"
                self.assertTrue(path.exists(), f"missing {path}")
                css = path.read_text()
                self.assertIn("html.dark", css)
                for weight in DARK_WEIGHTS:
                    self.assertIn(
                        f"--color-primary-{weight}: {palette['dark'][weight]};", css,
                        f"{slug}.css is out of step with ACCENTS at weight {weight}",
                    )

    def test_no_orphaned_stylesheets(self):
        on_disk = {p.stem for p in CSS_DIR.glob("*.css")}
        self.assertEqual(on_disk, set(ACCENTS))

    # --- Unfold's in-place mutation ---

    def test_accent_palette_returns_a_fresh_dict(self):
        """Unfold's `_get_colors` rewrites the dict it is handed
        (`colors[name][weight] = convert_color(value)`). Returning the registry's
        own dict would let the first request permanently recolour the admin."""
        request = type("R", (), {"user": None})()

        first = accent_palette(request)
        second = accent_palette(request)
        self.assertIsNot(first, second)

        first["600"] = "#000000"
        self.assertNotEqual(ACCENTS[DEFAULT_ACCENT]["light"]["600"], "#000000")
        self.assertNotEqual(accent_palette(request)["600"], "#000000")


class AccentPickerViewTests(TestCase):
    def setUp(self):
        # Migration 0026 seeds a Default team; these tests manage their own.
        Team.objects.all().delete()
        self.team = Team.objects.create(name="Alpha")

        self.user = User.objects.create_user('alice', 'a@x', 'pw', is_staff=True)
        self.user.teams.add(self.team)
        self.user.user_permissions.add(
            Permission.objects.get(
                content_type=ContentType.objects.get_for_model(Source),
                codename='view_source',
            )
        )

        self.client = Client()
        self.client.force_login(self.user)

    def _primary_600(self, body):
        import re
        match = re.search(r'--color-primary-600: ([^;]+);', body)
        self.assertIsNotNone(match, "no primary-600 emitted into the page")
        return match.group(1).strip()

    # --- Defaults ---

    def test_user_without_a_preference_gets_the_default(self):
        self.assertFalse(UserPreference.objects.filter(user=self.user).exists())

        body = self.client.get('/admin/').content.decode()
        self.assertEqual(
            self._primary_600(body),
            _css_colour(ACCENTS[DEFAULT_ACCENT]["light"]["600"]),
        )
        self.assertIn(f'accent/{DEFAULT_ACCENT}.css', body)

    # --- Round trip ---

    def test_choosing_an_accent_persists_and_recolours(self):
        resp = self.client.post(
            '/admin/set-accent/', {'accent': 'purple'}, HTTP_REFERER='/admin/screens/source/',
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp['Location'], '/admin/screens/source/')

        self.assertEqual(
            UserPreference.objects.get(user=self.user).accent, 'purple',
        )

        body = self.client.get('/admin/').content.decode()
        self.assertEqual(
            self._primary_600(body), _css_colour(ACCENTS['purple']["light"]["600"]),
        )
        self.assertIn('accent/purple.css', body)

    def test_changing_accent_twice_updates_the_same_row(self):
        for slug in ('purple', 'teal'):
            self.client.post('/admin/set-accent/', {'accent': slug})
        self.assertEqual(UserPreference.objects.filter(user=self.user).count(), 1)
        self.assertEqual(UserPreference.objects.get(user=self.user).accent, 'teal')

    def test_preference_does_not_leak_between_users(self):
        """The counterpart to test_accent_palette_returns_a_fresh_dict, at the
        HTTP level: one user's choice must not recolour anyone else's admin."""
        self.client.post('/admin/set-accent/', {'accent': 'amber'})

        other = User.objects.create_user('bob', 'b@x', 'pw', is_staff=True)
        other.teams.add(self.team)
        other_client = Client()
        other_client.force_login(other)

        body = other_client.get('/admin/').content.decode()
        self.assertEqual(
            self._primary_600(body),
            _css_colour(ACCENTS[DEFAULT_ACCENT]["light"]["600"]),
        )

    # --- Rejections ---

    def test_unknown_accent_is_rejected(self):
        resp = self.client.post('/admin/set-accent/', {'accent': 'chartreuse'})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(UserPreference.objects.filter(user=self.user).exists())

    def test_missing_accent_is_rejected(self):
        resp = self.client.post('/admin/set-accent/', {})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(UserPreference.objects.filter(user=self.user).exists())

    def test_get_is_not_allowed(self):
        """State-changing endpoint: unlike set-active-team, this writes a row."""
        self.assertEqual(self.client.get('/admin/set-accent/').status_code, 405)

    def test_anonymous_is_sent_to_login(self):
        resp = Client().post('/admin/set-accent/', {'accent': 'purple'})
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/admin/login/', resp['Location'])

    def test_non_staff_cannot_set_an_accent(self):
        plain = User.objects.create_user('carol', 'c@x', 'pw', is_staff=False)
        client = Client()
        client.force_login(plain)
        resp = client.post('/admin/set-accent/', {'accent': 'purple'})
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(UserPreference.objects.filter(user=plain).exists())

    def test_unknown_slug_on_an_existing_row_degrades_to_default(self):
        """A palette retired after someone chose it must not 500 their admin."""
        UserPreference.objects.create(user=self.user, accent='retired-colour')
        body = self.client.get('/admin/').content.decode()
        self.assertEqual(
            self._primary_600(body),
            _css_colour(ACCENTS[DEFAULT_ACCENT]["light"]["600"]),
        )

    # --- Rendering ---

    def test_picker_renders_in_the_sidebar_user_menu(self):
        body = self.client.get('/admin/').content.decode()
        self.assertIn('accent-switch__dot', body)
        self.assertIn('/admin/set-accent/', body)
        self.assertIn('value="blue"', body)
        self.assertIn('csrfmiddlewaretoken', body)
        for palette in ACCENTS.values():
            self.assertIn(f'aria-label="{palette["label"]}"', body)

    def test_picker_renders_on_a_changelist_too(self):
        """The dashboard extends admin/base.html directly while changelists go
        via admin/base_site.html. Both reach the sidebar, and both must show the
        picker — this pair is why the extra_userlinks block was not usable."""
        body = self.client.get('/admin/screens/source/').content.decode()
        self.assertIn('accent-switch__dot', body)

    def test_active_swatch_is_marked_for_assistive_tech(self):
        """Selection cannot be signalled by colour here — the control *is* colour."""
        self.client.post('/admin/set-accent/', {'accent': 'rose'})
        body = self.client.get('/admin/').content.decode()
        self.assertIn('value="rose"', body)
        self.assertRegex(body, r'value="rose"[^>]*aria-pressed="true"')
        self.assertRegex(body, r'value="blue"[^>]*aria-pressed="false"')

    def test_staff_user_with_no_teams_can_still_choose(self):
        """Covers the middleware bypass: without it these users get the no-team
        403 page instead of reaching the view."""
        loner = User.objects.create_user('dan', 'd@x', 'pw', is_staff=True)
        client = Client()
        client.force_login(loner)

        resp = client.post('/admin/set-accent/', {'accent': 'green'})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(UserPreference.objects.get(user=loner).accent, 'green')

    # --- Helpers ---

    def test_accent_slug_is_cached_on_the_request(self):
        """Two Unfold callables need it per render; it should cost one query."""
        UserPreference.objects.create(user=self.user, accent='teal')
        request = type("R", (), {"user": self.user})()

        with self.assertNumQueries(1):
            self.assertEqual(accent_slug(request), 'teal')
            self.assertEqual(accent_slug(request), 'teal')

    def test_picker_items_are_empty_for_non_staff(self):
        plain = User.objects.create_user('erin', 'e@x', 'pw', is_staff=False)
        request = type("R", (), {"user": plain})()
        self.assertEqual(accent_picker_items(request), [])


class UnfoldCouplingTests(TestCase):
    """Upgrade tripwire.

    These assert django-unfold internals that the accent feature depends on but
    that no rendered-page test can see. They are *meant* to fail when unfold is
    upgraded. When one does, do not delete it — instead:

      1. Re-diff the three forked templates under templates/unfold/helpers/
         (navigation_user, userlinks, unauthenticated_header) against the new
         vendor copies and re-apply this project's changes.
      2. Re-check the coupling list in CLAUDE.md, "Admin UI".
      3. Update the assertion to match the new reality.
    """

    def test_colours_are_still_emitted_as_root_custom_properties(self):
        skeleton = (UNFOLD_TEMPLATES / "layouts" / "skeleton.html").read_text()
        self.assertIn('id="unfold-theme-colors"', skeleton)
        self.assertIn("--color-{{ name }}-{{ weight }}", skeleton)

    def test_dark_mode_is_still_driven_by_a_class_on_html(self):
        """The dark override stylesheets key on `html.dark`. If unfold moved to
        a media query, every palette would silently lose its dark ramp."""
        skeleton = (UNFOLD_TEMPLATES / "layouts" / "skeleton.html").read_text()
        self.assertIn("'dark': adminTheme === 'dark'", skeleton)

    def test_vendor_user_menu_still_has_the_shape_we_forked(self):
        vendor = (UNFOLD_TEMPLATES / "helpers" / "navigation_user.html").read_text()
        self.assertIn('unfold/helpers/theme_switch.html', vendor)
        self.assertIn('openUserLinks', vendor)

    def test_our_fork_only_adds_the_accent_include(self):
        vendor = (UNFOLD_TEMPLATES / "helpers" / "navigation_user.html").read_text()
        ours = (
            Path(__file__).resolve().parents[2]
            / "templates" / "unfold" / "helpers" / "navigation_user.html"
        ).read_text()

        self.assertIn('unfold/helpers/accent_switch.html', ours)

        def strip(text):
            """Drop blank lines, our added include, and our {% comment %} block."""
            kept, in_comment = [], False
            for raw in text.splitlines():
                line = raw.strip()
                if line.startswith('{% comment %}'):
                    in_comment = True
                    continue
                if line.startswith('{% endcomment %}'):
                    in_comment = False
                    continue
                if in_comment or not line or 'accent_switch' in line:
                    continue
                kept.append(line)
            return kept

        self.assertEqual(
            strip(ours), strip(vendor),
            "the fork of navigation_user.html has drifted beyond the accent "
            "include — re-copy the vendor template and re-add the include",
        )
