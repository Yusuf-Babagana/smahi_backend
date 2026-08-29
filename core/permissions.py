from rest_framework import permissions


class IsArtisan(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == 'artisan'


class IsBusiness(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == 'business'


class IsClient(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == 'client'


class IsAgent(permissions.BasePermission):
    def has_permission(self, request, view):
        # account_status gate is the actual enforcement of "must not perform
        # official Agent activities" while Pending Approval/rejected/
        # dismissed/suspended (Coordinator Dashboard spec) — role alone
        # isn't enough, since a newly Coordinator-created agent already has
        # role='agent' from the moment they're created, well before a
        # Coordinator approves them (CoordinatorCreateAgentView).
        return (
            request.user and request.user.is_authenticated
            and request.user.role == 'agent' and request.user.account_status == 'active'
        )


class IsStateAgent(permissions.BasePermission):
    """Agents and state coordinators overseeing artisans/clients within their
    own state. The account_status gate only applies to the 'agent' half —
    a state_coordinator's own status is a separate concern (see
    AdminCoordinatorStatusView), not something this permission checks."""

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.role == 'agent':
            return request.user.account_status == 'active'
        return request.user.role == 'state_coordinator'


class IsProfileOwner(permissions.BasePermission):
    """Object-level guard: only the user a profile belongs to may modify it."""

    def has_object_permission(self, request, view, obj):
        return obj.user == request.user


class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == 'admin'


class IsStateCoordinator(permissions.BasePermission):
    """Coordinator-only oversight of the agents within their own state —
    distinct from IsStateAgent, which agents and coordinators share for
    artisan/client scoping."""

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == 'state_coordinator'
