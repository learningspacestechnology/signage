from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch import receiver


class Team(models.Model):
    name = models.CharField(max_length=120, unique=True)
    members = models.ManyToManyField(
        "auth.User",
        through="TeamMembership",
        related_name="teams",
        blank=True,
    )

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name

    def owned_object_counts(self):
        return {
            "sources": self.sources.count(),
            "playlists": self.playlists.count(),
            "screens": self.screens.count(),
            "schedules": self.schedules.count(),
        }

    def blocking_deletion_reasons(self):
        reasons = []
        member_count = self.members.count()
        if member_count:
            reasons.append(f"{member_count} user(s) still assigned")
        for label, count in self.owned_object_counts().items():
            if count:
                reasons.append(f"{count} {label} still owned")
        return reasons


class TeamMembership(models.Model):
    user = models.ForeignKey("auth.User", on_delete=models.CASCADE)
    team = models.ForeignKey(Team, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("user", "team")

    def __str__(self):
        return f"{self.user} ∈ {self.team}"


@receiver(pre_delete, sender=Team)
def _block_team_deletion_if_not_empty(sender, instance, **kwargs):
    reasons = instance.blocking_deletion_reasons()
    if reasons:
        raise ValidationError(
            f"Cannot delete team '{instance.name}': " + "; ".join(reasons)
        )
