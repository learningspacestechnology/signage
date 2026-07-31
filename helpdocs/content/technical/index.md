# Technical Documentation

For people who administer {{ config.ADMIN_SITE_NAME }} rather than use it day to
day: granting access, commissioning displays, keeping the room integration
healthy, and working out why something isn't behaving.

Everything here is about the running application. If you're looking for how a
change gets made in the interface, the
[everyday help pages](help:users/getting-started) cover that and are worth
reading first — this set assumes them.

!!! note "Deployment is not covered here"
    Installing the stack, environment configuration, TLS, backups and upgrades
    live with the deployment repository and the people who have access to it.
    Nothing on these pages requires that access, and nothing here duplicates it.
    If a fix needs a configuration change, this documentation says so and tells
    you what to ask for.

## Where to start

- **[How access works](help:access-model)** — read this before granting anyone
  anything. The two authorisation layers are independent and it's easy to change
  the wrong one.
- **[Users and teams](help:users-and-teams)** — the actual procedures for
  onboarding and offboarding.
- **[Commissioning a display](help:device-commissioning)** — getting a new
  physical screen working.
- **[Room and building displays](help:room-displays)** — booking displays are
  administered entirely from here; the everyday pages don't cover them at all.
- **[Things that go wrong](help:troubleshooting)** — symptom-first, for when
  something is already broken.
