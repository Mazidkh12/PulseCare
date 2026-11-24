"""
Audit Logging Service (Step 9).

Provides a centralized, append-only audit logging function that captures
security, clinical, and administrative actions without storing sensitive
passwords, tokens, or full clinical text.
"""
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from .models import AuditLog

# Sensitive keys that must NEVER be persisted in audit metadata
SENSITIVE_KEYS = {
    "password",
    "token",
    "secret",
    "session_id",
    "session_key",
    "clinical_notes",
    "past_medical_history",
    "past_surgical_history",
    "family_history",
    "personal_history",
    "description",
    "history_of_present_illness",
    "chief_complaint",
    "physical_examination",
    "clinical_assessment",
    "treatment_plan",
    "general_instructions",
    "special_instructions",
    "notes",
}


def sanitize_metadata(metadata: dict) -> dict:
    """
    Strips passwords, tokens, full clinical narratives, and sensitive clinical
    notes from metadata dictionaries.
    """
    if not isinstance(metadata, dict):
        return {}
    clean = {}
    for k, v in metadata.items():
        if k.lower() in SENSITIVE_KEYS:
            continue
        clean[k] = v
    return clean


def log_audit_event(
    actor=None,
    action: str = "",
    obj=None,
    object_label: str = "",
    metadata: dict = None,
) -> AuditLog:
    """
    Central append-only audit logging helper.

    Parameters:
    - actor: User performing the action (or None for system events)
    - action: AuditLog.Action value (e.g. 'FINALIZE_CONSULTATION')
    - obj: Model instance affected (optional)
    - object_label: Brief non-sensitive description
    - metadata: Optional non-sensitive dictionary
    """
    content_type = None
    object_id = ""
    if obj is not None:
        try:
            content_type = ContentType.objects.get_for_model(obj)
            object_id = str(getattr(obj, "pk", ""))
        except Exception:
            pass
        if not object_label:
            object_label = str(obj)[:255]

    clean_meta = sanitize_metadata(metadata or {})

    return AuditLog.objects.create(
        actor=actor,
        action=action,
        content_type=content_type,
        object_id=object_id,
        object_label=object_label[:255],
        timestamp=timezone.now(),
        metadata=clean_meta,
    )
