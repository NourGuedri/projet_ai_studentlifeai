"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import ClothingForm from "@/components/ClothingForm";
import { Alert, Badge, Button, Card, EmptyState, Loading, PageHeader, btnClass, cx } from "@/components/ui";
import { api } from "@/lib/api";

export default function ClosetPage() {
  const [options, setOptions] = useState(null);
  const [items, setItems] = useState(null);
  const [category, setCategory] = useState("");
  const [form, setForm] = useState(null); // null | "new" | item en cours de modification
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setItems(await api.get(`/closet/items/${category ? `?category=${category}` : ""}`));
    } catch (err) { setError(err.message); }
  }, [category]);

  useEffect(() => { api.get("/closet/items/options/").then(setOptions).catch((e) => setError(e.message)); }, []);
  useEffect(() => { load(); }, [load]);

  async function remove(item) {
    if (!confirm(`Supprimer « ${item.name || `${item.item_type} ${item.color.toLowerCase()}`} » de votre dressing ?`)) return;
    try {
      await api.del(`/closet/items/${item.id}/`);
      await load();
    } catch (err) { setError(err.message); }
  }

  const pill = (value, text) => (
    <button key={value} onClick={() => setCategory(value)}
      className={cx("rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors",
        category === value ? "border-brand-600 bg-brand-600 text-white" : "border-brand-200 bg-white text-brand-700 hover:bg-brand-50")}>
      {text}
    </button>
  );

  return (
    <>
      <PageHeader title="Mon dressing"
        subtitle="Photographiez vos vêtements : l'IA reconnaît le type, la couleur et le style, vous vérifiez, puis elle compose vos tenues selon la météo."
        actions={
          <>
            <Link href="/closet/outfit" className={btnClass("secondary")}>Tenue du jour</Link>
            {!form && options && <Button onClick={() => setForm("new")}>Ajouter un vêtement</Button>}
          </>
        } />

      {form && options && (
        <div className="mb-6">
          <ClothingForm options={options} item={form === "new" ? null : form}
            onCancel={() => setForm(null)} onSaved={async () => { setForm(null); await load(); }} />
        </div>
      )}

      {options && (
        <div className="mb-5 flex flex-wrap gap-2">
          {pill("", "Tout")}
          {options.categories.map((c) => pill(c.value, c.label))}
        </div>
      )}
      <Alert>{error}</Alert>

      {!items ? (!error && <Loading />) : items.length === 0 ? (
        <EmptyState title={category ? "Rien dans cette catégorie" : "Votre dressing est vide"}
          text="Ajoutez quelques vêtements en photo pour recevoir des suggestions de tenue adaptées à la météo." />
      ) : (
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4 lg:grid-cols-4">
          {items.map((item) => (
            <li key={item.id}>
              <Card className="flex h-full flex-col overflow-hidden !p-0">
                <img src={item.image} alt={`${item.item_type} ${item.color.toLowerCase()}`} loading="lazy"
                  className="aspect-square w-full bg-brand-50 object-cover" />
                <div className="flex flex-1 flex-col gap-2 p-3">
                  <p className="truncate font-medium">{item.name || item.item_type}</p>
                  <div className="flex flex-wrap gap-1.5">
                    <Badge>{item.color}</Badge>
                    <Badge tone="green">{item.style}</Badge>
                    {item.ai_detected && <Badge tone="slate">IA</Badge>}
                  </div>
                  <div className="mt-auto flex gap-1 pt-1">
                    <Button size="sm" variant="ghost" onClick={() => { setForm(item); window.scrollTo({ top: 0, behavior: "smooth" }); }}>Modifier</Button>
                    <Button size="sm" variant="danger" onClick={() => remove(item)}>Supprimer</Button>
                  </div>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
