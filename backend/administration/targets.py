"""Find the formation or quiz a report points to."""
from learning.models import Formation, Quiz


def get_target(target_type, target_id):
    if target_type == "formation":
        return Formation.objects.select_related("teacher").filter(pk=target_id).first()
    if target_type == "quiz":
        return Quiz.objects.select_related("owner", "formation").filter(pk=target_id).first()
    return None


def target_owner(target):
    return target.teacher if isinstance(target, Formation) else target.owner


def target_link(report, target):
    if target is None:
        return ""
    formation_id = target.id if report.target_type == "formation" else target.formation_id
    return f"/learning/formations/{formation_id}" if formation_id else ""
