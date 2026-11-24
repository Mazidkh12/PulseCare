from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """
    Read-only audit trail administrator interface.
    Ordinary add, change, and delete operations are strictly prohibited to maintain
    medical-legal audit integrity.
    """

    list_display = (
        "timestamp",
        "actor",
        "action",
        "object_label",
        "object_id",
    )
    list_filter = ("action", "timestamp")
    search_fields = (
        "actor__username",
        "actor__first_name",
        "actor__last_name",
        "object_id",
        "object_label",
    )
    readonly_fields = (
        "timestamp",
        "actor",
        "action",
        "content_type",
        "object_id",
        "object_label",
        "metadata",
    )
    ordering = ("-timestamp",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        user = request.user
        if not user.is_authenticated:
            return False
        return (
            getattr(user, "is_clinic_admin", False)
            or getattr(user, "is_superuser", False)
            or getattr(user, "role", "") == "ADMIN"
        )
