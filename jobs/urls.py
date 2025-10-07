from django.urls import path
from . import views

urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", views.login, name="login"),
    path("oauth/google/", views.oauth_google, name="oauth_google"),
    
    path("jobs/", views.jobs_list_create, name="jobs_list_create"),
    path("jobs/<int:id>/", views.jobs_detail, name="jobs_detail"),
    
    path("applications/", views.applications_list_create, name="applications_list_create"),
    path("applications/<int:id>/", views.application_detail, name="application_detail"),
]
