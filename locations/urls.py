from django.urls import path
from . import views

urlpatterns = [
    path('countries/', views.CountryListView.as_view(), name='countries'),
    path('countries/<int:pk>/', views.CountryDetailView.as_view(), name='country-detail'),
    path('states/', views.StateListView.as_view(), name='states'),
    path('states/<int:pk>/', views.StateDetailView.as_view(), name='state-detail'),
    path('lgas/', views.LGAListView.as_view(), name='lgas'),
    path('search/', views.location_search, name='location-search'),
]