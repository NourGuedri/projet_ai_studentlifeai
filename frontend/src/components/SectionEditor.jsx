"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { Alert, Button, Card, EmptyState, Field, Input, Select, Textarea } from "./ui";

/** Generic add / edit / delete list used by every profile section (formation, skills, projects...). */
export default function SectionEditor({ config, items, onChange }) {
  const [editing, setEditing] = useState(null); // null | "new" | item
  const [form, setForm] = useState({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const value = (f) => form[f.name] ?? (f.options ? f.options[0][0] : "");
  const open = (item) => { setError(""); setEditing(item ?? "new"); setForm(item ? { ...item } : {}); };

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const body = {};
    for (const f of config.fields) {
      let v = value(f);
      if ((f.type === "number" || f.type === "date") && v === "") v = null;
      if (f.type === "number" && v !== null) v = Number(v);
      body[f.name] = v;
    }
    try {
      if (editing === "new") await api.post(`/profile/${config.endpoint}/`, body);
      else await api.patch(`/profile/${config.endpoint}/${editing.id}/`, body);
      setEditing(null);
      await onChange();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function remove(item) {
    if (!confirm("Supprimer cet élément ?")) return;
    await api.del(`/profile/${config.endpoint}/${item.id}/`);
    await onChange();
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">{config.label}</h2>
        {!editing && <Button onClick={() => open()}>{config.addLabel}</Button>}
      </div>

      {editing && (
        <Card>
          <form onSubmit={save} className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2"><Alert>{error}</Alert></div>
            {config.fields.map((f) => (
              <Field key={f.name} label={f.label} hint={f.hint} className={f.wide ? "sm:col-span-2" : ""}>
                {f.options ? (
                  <Select value={value(f)} onChange={(e) => setForm({ ...form, [f.name]: e.target.value })}>
                    {f.options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </Select>
                ) : f.type === "textarea" ? (
                  <Textarea value={form[f.name] ?? ""} onChange={(e) => setForm({ ...form, [f.name]: e.target.value })} />
                ) : (
                  <Input type={f.type || "text"} required={f.required} value={form[f.name] ?? ""} onChange={(e) => setForm({ ...form, [f.name]: e.target.value })} />
                )}
              </Field>
            ))}
            <div className="flex gap-2 sm:col-span-2">
              <Button type="submit" variant="success" loading={busy}>Enregistrer</Button>
              <Button variant="ghost" onClick={() => setEditing(null)}>Annuler</Button>
            </div>
          </form>
        </Card>
      )}

      {items.length === 0 && !editing ? (
        <EmptyState title={config.emptyTitle} text={config.emptyText} />
      ) : (
        <ul className="space-y-3">
          {items.map((item) => (
            <li key={item.id}>
              <Card className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-medium">{config.title(item)}</p>
                  {config.subtitle(item) && <p className="text-sm text-slate-600">{config.subtitle(item)}</p>}
                  {item.description && <p className="mt-1 line-clamp-3 whitespace-pre-line text-sm text-slate-600">{item.description}</p>}
                </div>
                <div className="flex shrink-0 gap-1">
                  <Button size="sm" variant="ghost" onClick={() => open(item)}>Modifier</Button>
                  <Button size="sm" variant="danger" onClick={() => remove(item)}>Supprimer</Button>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
