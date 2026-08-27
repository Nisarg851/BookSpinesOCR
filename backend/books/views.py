from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(["GET"])
def health(request):
    """Placeholder so the Expo app can confirm it reaches Django."""
    return Response({"status": "ok", "service": "shelfie"})
