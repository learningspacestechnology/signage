from django.apps import AppConfig
from django.core import checks


class ScreensConfig(AppConfig):
    name = 'screens'

    def ready(self):
        # `advertising` is the project package, not an installed app, so its
        # system checks are registered here.
        from advertising.password_auth import check_password_login_setting

        checks.register(check_password_login_setting, checks.Tags.security)
