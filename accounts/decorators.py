"""
Role-based Access Control (RBAC) Decorators for Views (Step 10A).
"""
from functools import wraps
from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied


def role_required(*allowed_roles):
    """
    Decorator for views that checks whether a user is authenticated and possesses
    at least one of the specified roles (or is a superuser / clinic administrator).

    Unauthenticated users are safely redirected to the login page.
    Authenticated users lacking the required role receive a 403 PermissionDenied error.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)

            user_role = getattr(request.user, "role", None)
            is_admin = getattr(request.user, "is_clinic_admin", False) or request.user.is_superuser

            # Superusers or ADMIN role can access if ADMIN is in allowed roles
            if is_admin and "ADMIN" in allowed_roles:
                return view_func(request, *args, **kwargs)

            if user_role in allowed_roles:
                return view_func(request, *args, **kwargs)

            raise PermissionDenied("You do not have permission to access this page.")

        return _wrapped_view

    return decorator
