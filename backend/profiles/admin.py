from django.contrib import admin

from .models import Certification, Education, Experience, Language, Project, Skill, StudentProfile

for model in (StudentProfile, Education, Skill, Project, Experience, Certification, Language):
    admin.site.register(model)
