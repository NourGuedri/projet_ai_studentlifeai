from rest_framework.permissions import BasePermission


def is_teacher(user):
    return bool(user and user.is_authenticated and user.role in ("teacher", "admin"))


class IsTeacher(BasePermission):
    message = "Réservé aux enseignants."

    def has_permission(self, request, view):
        return is_teacher(request.user)


class IsAdminRole(BasePermission):
    message = "Réservé aux administrateurs."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.role == "admin")
