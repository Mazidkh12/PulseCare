from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Custom User Admin configuration to manage the custom User model
    and expose the clinic role field.
    """

    list_display = (
        'username',
        'email',
        'first_name',
        'last_name',
        'role',
        'is_staff',
        'is_active',
    )
    list_filter = ('role', 'is_staff', 'is_superuser', 'is_active', 'groups')
    search_fields = ('username', 'first_name', 'last_name', 'email')
    ordering = ('username',)

    # Add role field to the edit form
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Clinic Role', {'fields': ('role',)}),
    )

    # Add role field to the creation form
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Clinic Role', {
            'classes': ('wide',),
            'fields': ('role',),
        }),
    )
