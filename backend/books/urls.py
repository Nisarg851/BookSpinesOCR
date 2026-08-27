from django.urls import path

from .views import CatalogBookList, LibraryEntryList, health

urlpatterns = [
    path("health/", health, name="health"),
    path("catalog/", CatalogBookList.as_view(), name="catalog-list"),
    path("library/", LibraryEntryList.as_view(), name="library-list"),
]
