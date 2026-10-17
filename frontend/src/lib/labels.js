export const LEVELS = [["beginner", "Débutant"], ["intermediate", "Intermédiaire"], ["advanced", "Avancé"]];
export const LANG_LEVELS = [["beginner", "Débutant"], ["intermediate", "Intermédiaire"], ["advanced", "Courant"], ["native", "Langue maternelle"]];
export const EXP_TYPES = [["internship", "Stage"], ["job", "Emploi"], ["freelance", "Freelance"], ["other", "Autre"]];

export const label = (options, value) => options.find(([v]) => v === value)?.[1] ?? value;

export const fmtDate = (iso) =>
  iso ? new Date(iso).toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" }) : "";

export const MATERIAL_KINDS = {
  pdf: "PDF", document: "Document", slides: "Présentation", sheet: "Tableur",
  video: "Vidéo", audio: "Audio", image: "Image", archive: "Archive", other: "Fichier",
};

export function fmtSize(bytes) {
  if (!bytes) return "0 Ko";
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} Ko`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} Mo`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} Go`;
}
