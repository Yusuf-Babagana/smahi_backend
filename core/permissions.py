from rest_framework import permissions


class IsArtisan(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == 'artisan'


class IsClient(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == 'client'


class IsAgent(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == 'agent'


class IsStateAgent(permissions.BasePermission):
    """Agents and state coordinators overseeing artisans/clients within their own state."""

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role in ('agent', 'state_coordinator')
        )


class IsProfileOwner(permissions.BasePermission):
    """Object-level guard: only the user a profile belongs to may modify it."""

    def has_object_permission(self, request, view, obj):
        return obj.user == request.user


class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == 'admin'
