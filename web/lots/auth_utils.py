import os

from django.contrib.auth.mixins import LoginRequiredMixin


def is_auth_disabled() -> bool:
    value = (os.getenv("DISABLE_AUTH") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


class OptionalLoginRequiredMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if is_auth_disabled():
            return super(LoginRequiredMixin, self).dispatch(request, *args, **kwargs)
        return super().dispatch(request, *args, **kwargs)
