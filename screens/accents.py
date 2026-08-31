"""Admin accent colour palettes.

The single source of truth for the per-user accent picker. Each palette carries
two ramps, and the reason for that is not obvious:

Unfold uses ``--color-primary-500`` for text on white (``text-primary-500``,
24 uses in its templates) *and* for text on near-black (``dark:text-primary-500``,
26 uses). No single mid-tone clears WCAG AA 4.5:1 against both — anything light
enough for the dark background is too light for the white one. Unfold's own
purple splits the difference and misses both (4.12:1 and 4.30:1), which is the
accessibility complaint that prompted this module.

So ``light`` is the full ramp written into ``:root`` and tuned for light
backgrounds, and ``dark`` overrides only the three slots that get used on dark
backgrounds, tuned for those. The override is delivered by a stylesheet whose
``html.dark`` selector out-ranks Unfold's ``:root``. See CLAUDE.md, "Admin UI",
for the coupling this creates with Unfold's internals.

Ramps are Tailwind's, stepped one or two stops darker so slot 500 clears AA on
white. Do not hand-edit a hex here: ``screens/tests/test_accent_picker.py``
recomputes every contrast ratio and will name the slot that drifted.
"""

#: Weight keys Unfold emits, in ramp order. All 11 must be present in ``light``.
WEIGHTS = ("50", "100", "200", "300", "400", "500", "600", "700", "800", "900", "950")

#: Slots that appear on dark backgrounds and so need a lighter value there.
#: 500 and 400 are Unfold's own (`dark:text-primary-500`, `dark:bg-primary-500`,
#: `dark:text-primary-400`); 400 and 300 are also used by this project's
#: `admin_table_links.css` under `html.dark`.
DARK_WEIGHTS = ("300", "400", "500")

DEFAULT_ACCENT = "graphite"

ACCENTS = {
    "graphite": {
        "label": "High contrast",
        "light": {
            "50": "#f1f5f9",
            "100": "#e2e8f0",
            "200": "#cbd5e1",
            "300": "#94a3b8",
            "400": "#64748b",
            "500": "#475569",
            "600": "#334155",
            "700": "#1e293b",
            "800": "#0f172a",
            "900": "#020617",
            "950": "#01040e",
        },
        "dark": {
            "300": "#e2e8f0",
            "400": "#cbd5e1",
            "500": "#94a3b8",
        },
    },
    "purple": {
        "label": "Purple",
        "light": {
            "50": "#f3e8ff",
            "100": "#e9d5ff",
            "200": "#d8b4fe",
            "300": "#c084fc",
            "400": "#a855f7",
            "500": "#9333ea",
            "600": "#7e22ce",
            "700": "#6b21a8",
            "800": "#581c87",
            "900": "#3b0764",
            "950": "#25043e",
        },
        "dark": {
            "300": "#e9d5ff",
            "400": "#d8b4fe",
            "500": "#c084fc",
        },
    },
    "indigo": {
        "label": "Indigo",
        "light": {
            "50": "#e0e7ff",
            "100": "#c7d2fe",
            "200": "#a5b4fc",
            "300": "#818cf8",
            "400": "#6366f1",
            "500": "#4f46e5",
            "600": "#4338ca",
            "700": "#3730a3",
            "800": "#312e81",
            "900": "#1e1b4b",
            "950": "#13112e",
        },
        "dark": {
            "300": "#c7d2fe",
            "400": "#a5b4fc",
            "500": "#818cf8",
        },
    },
    "blue": {
        "label": "Blue",
        "light": {
            "50": "#dbeafe",
            "100": "#bfdbfe",
            "200": "#93c5fd",
            "300": "#60a5fa",
            "400": "#3b82f6",
            "500": "#2563eb",
            "600": "#1d4ed8",
            "700": "#1e40af",
            "800": "#1e3a8a",
            "900": "#172554",
            "950": "#0e1734",
        },
        "dark": {
            "300": "#bfdbfe",
            "400": "#93c5fd",
            "500": "#60a5fa",
        },
    },
    "teal": {
        "label": "Teal",
        "light": {
            "50": "#99f6e4",
            "100": "#5eead4",
            "200": "#2dd4bf",
            "300": "#14b8a6",
            "400": "#0d9488",
            "500": "#0f766e",
            "600": "#115e59",
            "700": "#134e4a",
            "800": "#042f2e",
            "900": "#021d1d",
            "950": "#021212",
        },
        "dark": {
            "300": "#5eead4",
            "400": "#2dd4bf",
            "500": "#14b8a6",
        },
    },
    "green": {
        "label": "Green",
        "light": {
            "50": "#bbf7d0",
            "100": "#86efac",
            "200": "#4ade80",
            "300": "#22c55e",
            "400": "#16a34a",
            "500": "#15803d",
            "600": "#166534",
            "700": "#14532d",
            "800": "#052e16",
            "900": "#031d0e",
            "950": "#021208",
        },
        "dark": {
            "300": "#86efac",
            "400": "#4ade80",
            "500": "#22c55e",
        },
    },
    "amber": {
        "label": "Amber",
        "light": {
            "50": "#fde68a",
            "100": "#fcd34d",
            "200": "#fbbf24",
            "300": "#f59e0b",
            "400": "#d97706",
            "500": "#b45309",
            "600": "#92400e",
            "700": "#78350f",
            "800": "#451a03",
            "900": "#2b1002",
            "950": "#1b0a01",
        },
        "dark": {
            "300": "#fcd34d",
            "400": "#fbbf24",
            "500": "#f59e0b",
        },
    },
    "rose": {
        "label": "Rose",
        "light": {
            "50": "#ffe4e6",
            "100": "#fecdd3",
            "200": "#fda4af",
            "300": "#fb7185",
            "400": "#f43f5e",
            "500": "#e11d48",
            "600": "#be123c",
            "700": "#9f1239",
            "800": "#881337",
            "900": "#4c0519",
            "950": "#2f0310",
        },
        "dark": {
            "300": "#fecdd3",
            "400": "#fda4af",
            "500": "#fb7185",
        },
    },
    "pink": {
        "label": "Pink",
        "light": {
            "50": "#fce7f3",
            "100": "#fbcfe8",
            "200": "#f9a8d4",
            "300": "#f472b6",
            "400": "#ec4899",
            "500": "#db2777",
            "600": "#be185d",
            "700": "#9d174d",
            "800": "#831843",
            "900": "#500724",
            "950": "#320416",
        },
        "dark": {
            "300": "#fbcfe8",
            "400": "#f9a8d4",
            "500": "#f472b6",
        },
    },
}


def resolve(slug):
    """The palette for `slug`, falling back to the default for anything unknown.

    Used on the render path, where a slug that is no longer in the registry (a
    palette retired after someone chose it) must degrade to the default rather
    than raise. The write path validates instead — see `set_accent_view`.
    """
    return ACCENTS.get(slug) or ACCENTS[DEFAULT_ACCENT]


def light_ramp(slug):
    """A **fresh** copy of the light ramp, for Unfold's ``COLORS`` callable.

    Unfold's `AdminSite._get_colors` rewrites the dict it is given in place
    (`colors[name][weight] = convert_color(value)`), so handing it the registry
    constant would let one request permanently rewrite the palette for every
    later one. Copy, always.
    """
    return dict(resolve(slug)["light"])


def swatches(slug):
    """(light, dark) dot colours for the picker.

    The menu is white in light mode and near-black in dark mode, so a single
    swatch colour would be invisible in one of them. `600` reads on white,
    `400` reads on the dark panel.
    """
    palette = resolve(slug)
    return palette["light"]["600"], palette["dark"]["400"]
