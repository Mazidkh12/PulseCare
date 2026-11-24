from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone


class AuditLog(models.Model):
    """
    Append-only system audit log tracking security, clinical, and administrative actions.
    """

    class Action(models.TextChoices):
        CREATE = "CREATE", "Create"
        UPDATE = "UPDATE", "Update"
        DELETE = "DELETE", "Delete"
        FINALIZE_CONSULTATION = "FINALIZE_CONSULTATION", "Finalize Consultation"
        ISSUE_PRESCRIPTION = "ISSUE_PRESCRIPTION", "Issue Prescription"
        CREATE_DIAGNOSIS = "CREATE_DIAGNOSIS", "Create Diagnosis"
        UPDATE_DIAGNOSIS = "UPDATE_DIAGNOSIS", "Update Diagnosis"
        CANCEL_APPOINTMENT = "CANCEL_APPOINTMENT", "Cancel Appointment"
        LOGIN = "LOGIN", "Login"
        LOGOUT = "LOGOUT", "Logout"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
        help_text="User who initiated or performed the action (null if system or user was deleted).",
    )
    action = models.CharField(
        max_length=50,
        choices=Action.choices,
        db_index=True,
        help_text="Type of action performed.",
    )
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Content type of the affected model.",
    )
    object_id = models.CharField(
        max_length=100,
        blank=True,
        db_index=True,
        help_text="Primary key identifier of the affected record.",
    )
    object_label = models.CharField(
        max_length=255,
        blank=True,
        help_text="Short non-sensitive human-readable descriptor of the affected entity.",
    )
    timestamp = models.DateTimeField(
        default=timezone.now,
        editable=False,
        db_index=True,
        help_text="Timestamp when the action was recorded.",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Optional non-sensitive structured metadata.",
    )

    class Meta:
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["actor", "-timestamp"]),
            models.Index(fields=["action", "-timestamp"]),
            models.Index(fields=["content_type", "object_id"]),
        ]

    def __str__(self):
        actor_name = self.actor.username if self.actor else "System"
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {actor_name} -> {self.get_action_display()}: {self.object_label}"
