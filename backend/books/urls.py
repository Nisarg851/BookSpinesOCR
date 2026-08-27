from django.urls import path

from .views import (
    CatalogBookList,
    LibraryEntryList,
    health,
    photo_create,
    photo_detail,
    spine_confirm,
)

urlpatterns = [
    path("health/", health, name="health"),
    path("catalog/", CatalogBookList.as_view(), name="catalog-list"),
    path("library/", LibraryEntryList.as_view(), name="library-list"),
    path("photos/", photo_create, name="photo-create"),
    path("photos/<int:photo_id>/", photo_detail, name="photo-detail"),
    path("spines/<int:spine_id>/confirm/", spine_confirm, name="spine-confirm"),
    # Back-compat for older Expo builds.
    path("detect/", photo_create, name="detect-books"),
]
