from rest_framework.permissions import SAFE_METHODS, BasePermission

from core.models import User


class CanCreateProfile(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not request.user.is_active:
            return False
        if request.method in SAFE_METHODS:
            return True
        if User.UserRole.ADMIN == user.role:
            return True
        return False


class CanUpdateProfile(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not request.user.is_active:
            return False
        if request.method in SAFE_METHODS:
            return True
        if User.UserRole.ADMIN == user.role:
            return True
        return False
