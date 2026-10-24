"use client";
import { useEffect, useState } from "react";
import { Alert, Badge, Button, Card, Field, Input, Select } from "@/components/ui";
import { api } from "@/lib/api";

/**
 * Ajout (photo -> détection IA -> validation) ou modification d'un vêtement.
 * L'IA ne fait que proposer : l'étudiant vérifie et corrige avant d'enregistrer.
 */
export default function ClothingForm({ options, item, onSaved, onCancel }) {
  const editing = Boolean(item);
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(item?.image || "");
  const [form, setForm] = useState({
    name: item?.name || "", item_type: item?.item_type || "", color: item?.color || "", style: item?.style || "",
  });
  const [ai, setAi] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  useEffect(() => {
    if (!file) return;
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  async function pick(e) {
    const chosen = e.target.files?.[0];
    if (!chosen) return;
    setFile(chosen);
    setAi(null);
    setError("");
    setNotice("");
    setAnalyzing(true);
    try {
      const data = new FormData();
      data.append("image", chosen);
      const result = await api.form("/closet/items/analyze/", data);
      setAi(result);
      setForm((f) => ({ ...f, item_type: result.item_type, color: result.color, style: result.style }));
    } catch (err) {
      // 503 : modèle pas encore entraîné / PyTorch absent -> on continue en saisie manuelle
      if (err.status === 503) setNotice(err.message);
      else setError(err.message);
    } finally {
      setAnalyzing(false);
    }
  }

  async function submit(e) {
    e.preventDefault();
    setError("");
    if (!editing && !file) return setError("Ajoutez une photo du vêtement.");
    if (!form.item_type || !form.color || !form.style) return setError("Choisissez le type, la couleur et le style.");
    setBusy(true);
    try {
      let saved;
      if (editing) {
        saved = await api.patch(`/closet/items/${item.id}/`, form);
      } else {
        const data = new FormData();
        data.append("image", file);
        Object.entries(form).forEach(([k, v]) => data.append(k, v));
        data.append("ai_detected", ai ? "true" : "false");
        if (ai) data.append("ai_confidence", String(ai.confidence));
        saved = await api.form("/closet/items/", data);
      }
      await onSaved(saved);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <Card>
      <form onSubmit={submit} className="grid gap-5 sm:grid-cols-[200px_1fr]">
        <div className="sm:col-span-2"><Alert>{error}</Alert></div>

        <div>
          <div className="flex aspect-square w-full items-center justify-center overflow-hidden rounded-xl border border-dashed border-brand-200 bg-brand-50">
            {preview
              ? <img src={preview} alt="Aperçu du vêtement" className="h-full w-full object-cover" />
              : <span className="px-3 text-center text-xs text-slate-500">Aucune photo</span>}
          </div>
          {!editing && (
            <label className="mt-3 block">
              <span className="sr-only">Photo du vêtement</span>
              <input type="file" accept="image/*" onChange={pick}
                className="block w-full text-xs text-slate-600 file:mr-3 file:rounded-lg file:border-0 file:bg-brand-600 file:px-3 file:py-2 file:text-sm file:font-medium file:text-white hover:file:bg-brand-700" />
            </label>
          )}
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          {analyzing && <p className="text-sm text-brand-700 sm:col-span-2" role="status">Analyse de la photo en cours…</p>}
          {ai && (
            <div className="flex flex-wrap items-center gap-2 sm:col-span-2">
              <Badge tone={ai.uncertain ? "amber" : "green"}>Détecté par l'IA · {Math.round(ai.confidence * 100)} %</Badge>
              <span className="text-xs text-slate-600">
                {ai.uncertain ? "L'IA n'est pas sûre : vérifiez bien." : "Vérifiez et corrigez si besoin."}
              </span>
            </div>
          )}
          {notice && <div className="sm:col-span-2"><Alert tone="info">{notice}</Alert></div>}

          <Field label="Type de vêtement">
            <Select required value={form.item_type} onChange={set("item_type")}>
              <option value="">Choisir…</option>
              {options.categories.map((c) => (
                <optgroup key={c.value} label={c.label}>
                  {options.types[c.value].map((t) => <option key={t} value={t}>{t}</option>)}
                </optgroup>
              ))}
            </Select>
          </Field>
          <Field label="Couleur principale">
            <Select required value={form.color} onChange={set("color")}>
              <option value="">Choisir…</option>
              {options.colors.map((c) => <option key={c} value={c}>{c}</option>)}
            </Select>
          </Field>
          <Field label="Style">
            <Select required value={form.style} onChange={set("style")}>
              <option value="">Choisir…</option>
              {options.styles.map((s) => <option key={s} value={s}>{s}</option>)}
            </Select>
          </Field>
          <Field label="Nom (facultatif)">
            <Input value={form.name} onChange={set("name")} maxLength={80} placeholder="Ex. : T-shirt du concert" />
          </Field>

          <div className="flex gap-2 sm:col-span-2">
            <Button type="submit" variant="success" loading={busy} disabled={analyzing}>
              {editing ? "Enregistrer les modifications" : "Ajouter au dressing"}
            </Button>
            <Button variant="ghost" onClick={onCancel}>Annuler</Button>
          </div>
        </div>
      </form>
    </Card>
  );
}
