from rest_framework import serializers

from .models import (
    Certification,
    Education,
    Experience,
    Language,
    Project,
    Skill,
    StudentProfile,
)


def _item_serializer(model):
    meta = type("Meta", (), {"model": model, "exclude": ("profile",)})
    return type(f"{model.__name__}Serializer", (serializers.ModelSerializer,), {"Meta": meta})


EducationSerializer = _item_serializer(Education)
SkillSerializer = _item_serializer(Skill)
ProjectSerializer = _item_serializer(Project)
ExperienceSerializer = _item_serializer(Experience)
CertificationSerializer = _item_serializer(Certification)
LanguageSerializer = _item_serializer(Language)


class ProfileSerializer(serializers.ModelSerializer):
    educations = EducationSerializer(many=True, read_only=True)
    skills = SkillSerializer(many=True, read_only=True)
    projects = ProjectSerializer(many=True, read_only=True)
    experiences = ExperienceSerializer(many=True, read_only=True)
    certifications = CertificationSerializer(many=True, read_only=True)
    languages = LanguageSerializer(many=True, read_only=True)
    cv_url = serializers.SerializerMethodField()
    completion = serializers.SerializerMethodField()

    class Meta:
        model = StudentProfile
        fields = (
            "headline", "university", "study_level", "city", "bio", "linkedin_url", "github_url",
            "cv_url", "cv_uploaded_at", "completion",
            "educations", "skills", "projects", "experiences", "certifications", "languages",
        )
        read_only_fields = ("cv_uploaded_at",)

    def get_cv_url(self, obj):
        if not obj.cv_file:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(obj.cv_file.url) if request else obj.cv_file.url

    def get_completion(self, obj):
        checks = [
            ("Titre du profil", bool(obj.headline)),
            ("Présentation", bool(obj.bio)),
            ("Établissement", bool(obj.university)),
            ("Formation", obj.educations.exists()),
            ("Compétences", obj.skills.exists()),
            ("Projets", obj.projects.exists()),
            ("Expériences", obj.experiences.exists()),
            ("Certifications", obj.certifications.exists()),
            ("Langues", obj.languages.exists()),
            ("CV importé", bool(obj.cv_file)),
        ]
        done = sum(1 for _, ok in checks if ok)
        return {"percent": round(100 * done / len(checks)), "missing": [label for label, ok in checks if not ok]}


class CVApplySerializer(serializers.Serializer):
    headline = serializers.CharField(required=False, allow_blank=True, max_length=120)
    bio = serializers.CharField(required=False, allow_blank=True)
    linkedin_url = serializers.URLField(required=False, allow_blank=True)
    github_url = serializers.URLField(required=False, allow_blank=True)
    skills = SkillSerializer(many=True, required=False)
    languages = LanguageSerializer(many=True, required=False)
    educations = EducationSerializer(many=True, required=False)
    experiences = ExperienceSerializer(many=True, required=False)
    projects = ProjectSerializer(many=True, required=False)
    certifications = CertificationSerializer(many=True, required=False)
