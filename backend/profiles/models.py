from django.conf import settings
from django.db import models


class StudentProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    headline = models.CharField(max_length=120, blank=True)
    university = models.CharField(max_length=150, blank=True)
    study_level = models.CharField(max_length=80, blank=True)
    city = models.CharField(max_length=80, blank=True)
    bio = models.TextField(blank=True)
    linkedin_url = models.URLField(blank=True)
    github_url = models.URLField(blank=True)
    cv_file = models.FileField(upload_to="cvs/%Y/%m/", blank=True)
    cv_text = models.TextField(blank=True)
    cv_uploaded_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profil de {self.user}"


class ProfileItem(models.Model):
    profile = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name="%(class)ss")

    class Meta:
        abstract = True


class Education(ProfileItem):
    school = models.CharField(max_length=150)
    degree = models.CharField(max_length=150, blank=True)
    field = models.CharField(max_length=150, blank=True)
    start_year = models.PositiveSmallIntegerField(null=True, blank=True)
    end_year = models.PositiveSmallIntegerField(null=True, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["-end_year", "-start_year"]


class Skill(ProfileItem):
    LEVELS = [("beginner", "Débutant"), ("intermediate", "Intermédiaire"), ("advanced", "Avancé")]
    name = models.CharField(max_length=80)
    level = models.CharField(max_length=15, choices=LEVELS, default="intermediate")

    class Meta:
        ordering = ["name"]


class Project(ProfileItem):
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    tech_stack = models.CharField(max_length=250, blank=True)
    url = models.URLField(blank=True)

    class Meta:
        ordering = ["-id"]


class Experience(ProfileItem):
    TYPES = [("internship", "Stage"), ("job", "Emploi"), ("freelance", "Freelance"), ("other", "Autre")]
    position = models.CharField(max_length=150)
    company = models.CharField(max_length=150, blank=True)
    type = models.CharField(max_length=12, choices=TYPES, default="internship")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)  # empty = ongoing
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["-start_date", "-id"]


class Certification(ProfileItem):
    name = models.CharField(max_length=150)
    issuer = models.CharField(max_length=150, blank=True)
    issue_date = models.DateField(null=True, blank=True)
    credential_url = models.URLField(blank=True)

    class Meta:
        ordering = ["-issue_date", "-id"]


class Language(ProfileItem):
    LEVELS = [("beginner", "Débutant"), ("intermediate", "Intermédiaire"), ("advanced", "Courant"), ("native", "Langue maternelle")]
    name = models.CharField(max_length=60)
    level = models.CharField(max_length=15, choices=LEVELS, default="intermediate")

    class Meta:
        ordering = ["name"]
