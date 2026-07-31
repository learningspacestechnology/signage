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

    # Declared explicitly only to avoid a models.W042 warning about the
    # auto-created key. Nothing reads it — there is no table.
    id = models.AutoField(primary_key=True)

    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ('view_technical_docs', 'Can view technical help documentation'),
        ]
        verbose_name = 'help documentation access'
        verbose_name_plural = 'help documentation access'
