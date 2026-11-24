from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from accounts.views import role_required
from .models import AuditLog


@role_required("ADMIN")
def audit_log_list_view(request):
    """
    Administrator-facing append-only audit log explorer with keyword search,
    action filtering, date range constraints, and pagination.
    Does NOT generate new audit logs when querying or viewing logs.
    """
    query = request.GET.get("q", "").strip()
    action_filter = request.GET.get("action", "").strip()
    start_date = request.GET.get("start_date", "").strip()
    end_date = request.GET.get("end_date", "").strip()

    qs = AuditLog.objects.select_related("actor", "content_type").order_by("-timestamp")

    if query:
        qs = qs.filter(
            Q(actor__username__icontains=query)
            | Q(object_label__icontains=query)
            | Q(object_id__icontains=query)
            | Q(action__icontains=query)
        )

    if action_filter and action_filter in dict(AuditLog.Action.choices):
        qs = qs.filter(action=action_filter)

    if start_date:
        qs = qs.filter(timestamp__date__gte=start_date)

    if end_date:
        qs = qs.filter(timestamp__date__lte=end_date)

    paginator = Paginator(qs, 20)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "audit/audit_log_list.html",
        {
            "page_obj": page_obj,
            "query": query,
            "action_filter": action_filter,
            "start_date": start_date,
            "end_date": end_date,
            "actions": AuditLog.Action.choices,
            "total_logs": AuditLog.objects.count(),
        },
    )


@role_required("ADMIN")
def audit_log_detail_view(request, pk):
    """
    Read-only detailed view for a single audit log entry.
    Exposes only safe metadata without sensitive passwords, tokens, or clinical notes.
    """
    log_entry = get_object_or_404(
        AuditLog.objects.select_related("actor", "content_type"), pk=pk
    )

    return render(
        request,
        "audit/audit_log_detail.html",
        {
            "log": log_entry,
        },
    )
