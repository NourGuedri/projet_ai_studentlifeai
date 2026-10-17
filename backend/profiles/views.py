from pathlib import Path

from django.core.files.base import ContentFile
from django.utils import timezone
from rest_framework import generics, status, viewsets
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from common.text import TextExtractionError, extract_text_from_bytes

from . import cv_parser
from .models import Certification, Education, Experience, Language, Project, Skill, StudentProfile
from .serializers import (
    CertificationSerializer,
    CVApplySerializer,
    EducationSerializer,
    ExperienceSerializer,
    LanguageSerializer,
    ProfileSerializer,
    ProjectSerializer,
    SkillSerializer,
)

MAX_CV_SIZE = 5 * 1024 * 1024


def get_profile(user):
    profile, _ = StudentProfile.objects.get_or_create(user=user)
    return profile


class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = ProfileSerializer

    def get_object(self):
        return get_profile(self.request.user)


class ProfileItemViewSet(viewsets.ModelViewSet):
    model = None

    def get_queryset(self):
        return self.model.objects.filter(profile=get_profile(self.request.user))

    def perform_create(self, serializer):
        serializer.save(profile=get_profile(self.request.user))


def _viewset(model, serializer):
    return type(f"{model.__name__}ViewSet", (ProfileItemViewSet,), {"model": model, "serializer_class": serializer})


EducationViewSet = _viewset(Education, EducationSerializer)
SkillViewSet = _viewset(Skill, SkillSerializer)
ProjectViewSet = _viewset(Project, ProjectSerializer)
ExperienceViewSet = _viewset(Experience, ExperienceSerializer)
CertificationViewSet = _viewset(Certification, CertificationSerializer)
LanguageViewSet = _viewset(Language, LanguageSerializer)


class CVUploadView(APIView):
    """Upload a CV (PDF/DOCX) and return *suggested* profile data. Nothing is saved to the profile yet."""

    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        upload = request.FILES.get("file")
        if not upload:
            return Response({"detail": "Aucun fichier envoyé."}, status=status.HTTP_400_BAD_REQUEST)
        ext = Path(upload.name).suffix.lower()
        if ext not in (".pdf", ".docx"):
            return Response({"detail": "Formats acceptés : PDF ou DOCX."}, status=status.HTTP_400_BAD_REQUEST)
        if upload.size > MAX_CV_SIZE:
            return Response({"detail": "Fichier trop volumineux (5 Mo maximum)."}, status=status.HTTP_400_BAD_REQUEST)

        # Read the text from memory first: a file we cannot read never replaces the CV already saved.
        data = upload.read()
        try:
            text = extract_text_from_bytes(data, ext)
        except TextExtractionError as exc:
            return Response({"detail": str(exc)}, status=422)
        if not text.strip():
            return Response(
                {"detail": "Aucun texte trouvé. S'il s'agit d'un PDF scanné, utilisez une version texte (exportée depuis Word)."},
                status=422,
            )

        profile = get_profile(request.user)
        old_name = profile.cv_file.name
        profile.cv_file.save(upload.name, ContentFile(data), save=False)
        profile.cv_text = text
        profile.cv_uploaded_at = timezone.now()
        profile.save()
        if old_name and old_name != profile.cv_file.name:
            profile.cv_file.storage.delete(old_name)

        result, method = cv_parser.parse_cv(text)
        return Response({"method": method, "extracted": result, "cv_url": request.build_absolute_uri(profile.cv_file.url)})


class CVApplyView(APIView):
    """Save the (reviewed) extraction into the profile. Existing entries are not duplicated."""

    SECTIONS = {
        "skills": (Skill, ("name",)),
        "languages": (Language, ("name",)),
        "educations": (Education, ("school", "degree")),
        "experiences": (Experience, ("position", "company")),
        "projects": (Project, ("title",)),
        "certifications": (Certification, ("name",)),
    }

    def post(self, request):
        serializer = CVApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        profile = get_profile(request.user)

        for field in ("headline", "bio", "linkedin_url", "github_url"):
            if data.get(field) and not getattr(profile, field):
                setattr(profile, field, data[field])
        profile.save()

        created = {}
        for key, (model, lookup_fields) in self.SECTIONS.items():
            count = 0
            for item in data.get(key, []):
                lookup = {f: item.get(f, "") for f in lookup_fields}
                _, was_created = model.objects.get_or_create(profile=profile, defaults=dict(item), **lookup)
                count += int(was_created)
            created[key] = count
        return Response({"created": created, "profile": ProfileSerializer(profile, context={"request": request}).data})
