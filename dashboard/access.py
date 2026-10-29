from functools import wraps
from typing import Callable

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


ViewFunction = Callable[..., HttpResponse]


def role_required(*allowed_roles: str):
    """Require authentication and membership in an allowed role."""

    if not allowed_roles:
        raise ValueError("At least one allowed role must be provided.")

    def decorator(view_function: ViewFunction) -> ViewFunction:
        @login_required
        @wraps(view_function)
        def wrapped_view(
            request: HttpRequest,
            *args,
            **kwargs,
        ) -> HttpResponse:
            user = request.user

            # Django superusers can access all application views.
            if user.is_superuser:
                return view_function(request, *args, **kwargs)

            has_role = user.groups.filter(
                name__in=allowed_roles,
            ).exists()

            if not has_role:
                # Render directly so the custom page also works with DEBUG=True.
                return render(
                    request,
                    "dashboard/403.html",
                    status=403,
                )

            return view_function(request, *args, **kwargs)

        return wrapped_view

    return decorator