from django.conf import settings
from django.http import Http404
from django.views.static import serve
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class PublicConfigView(APIView):
    """Non-secret config the static frontend needs at runtime. The browser Google
    Maps key is meant to be public (restrict it by HTTP referrer in the Google
    Cloud console); serving it here keeps it out of the committed static site."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({"google_maps_browser_key": settings.GOOGLE_MAPS_BROWSER_KEY})


def frontend_file(request, path):
    """Serve the static frontend in dev (see the DEBUG block in config/urls.py).

    `django.views.static.serve` handles files and blocks path traversal, but has no
    notion of a directory index — so "" and "rider/" resolve to their index.html,
    which is what a plain static server would do.
    """
    root = settings.FRONTEND_DIR.resolve()
    if path == "" or path.endswith("/"):
        path = f"{path}index.html"
    elif (root / path).is_dir():
        path = f"{path}/index.html"

    # Resolve before touching the filesystem: a traversal path must 404 here rather
    # than reach `serve` and raise SuspiciousFileOperation.
    target = (root / path).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise Http404(f"No frontend file at {path!r}")
    return serve(request, path, document_root=root)
