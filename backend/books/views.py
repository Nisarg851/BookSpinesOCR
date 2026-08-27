from rest_framework import generics
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import CatalogBook, LibraryEntry
from .serializers import CatalogBookSerializer, LibraryEntrySerializer


@api_view(["GET"])
def health(request):
    """Placeholder so the Expo app can confirm it reaches Django."""
    return Response({"status": "ok", "service": "shelfie"})


class CatalogBookList(generics.ListAPIView):
    """Read-only catalog dump — useful for sanity-checking load_catalog."""

    queryset = CatalogBook.objects.all()
    serializer_class = CatalogBookSerializer


class LibraryEntryList(generics.ListAPIView):
    """Confirmed library for the single implicit user."""

    queryset = LibraryEntry.objects.select_related("catalog_book").all()
    serializer_class = LibraryEntrySerializer
