"""Automatic notifications that do not belong to any single module."""
from django.db.models.signals import post_save
from django.dispatch import receiver

from .services import notify


@receiver(post_save, sender="accounts.User", dispatch_uid="notify_welcome")
def welcome_new_user(sender, instance, created, raw=False, **kwargs):
    if created and not raw:
        notify(instance, "Bienvenue sur StudentLife AI", "Complétez votre profil pour profiter de toutes les fonctionnalités.", "/dashboard", "success")


@receiver(post_save, sender="learning.Enrollment", dispatch_uid="notify_teacher_enrollment")
def tell_teacher_about_enrollment(sender, instance, created, raw=False, **kwargs):
    formation = instance.formation
    if created and not raw and formation.teacher_id != instance.user_id:
        student = instance.user.get_full_name() or instance.user.email
        notify(formation.teacher, "Nouvelle inscription", f"{student} s'est inscrit(e) à « {formation.title} ».", f"/learning/formations/{formation.id}")
