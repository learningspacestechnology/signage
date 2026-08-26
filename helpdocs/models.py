from django.db import models


class HelpDocsAccess(models.Model):
    """Permission carrier only — deliberately has no table and no rows.

    The technical help set is gated on ``helpdocs.view_technical_docs``. A Django
    permission needs a ContentType to hang off, so this unmanaged model exists
    purely to create one. ``managed = False`` means no table is created, and
    ``default_permissions = ()`` suppresses the usual add/change/delete/view set
    so only the one meaningful permission appears in the Group form.

    This is the *capability* layer (Group + Permission), not the *tenancy* layer
    (Team) — see CLAUDE.md, "Teams (multi-tenancy) vs. Groups (capabilities)".
    """

    # Redundant since `DEFAULT_AUTO_FIELD` was added to `base_settings.py` — that
    # is what keeps models.W042 quiet project-wide now. Kept anyway: an explicit
    # AutoField deconstructs differently from an auto-created one (which carries
    # `auto_created=True` and `verbose_name='ID'`), so deleting it would ask for an
    # AlterField on an unmanaged model for no gain. Nothing reads it — there is no table.
    id = models.AutoField(primary_key=True)

    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ('view_technical_docs', 'Can view technical help documentation'),
        ]
        verbose_name = 'help documentation access'
        verbose_name_plural = 'help documentation access'
