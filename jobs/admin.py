from django.contrib import admin
from .models import User, JobListing, JobApplication
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    pass

admin.site.register(JobListing)
admin.site.register(JobApplication)

