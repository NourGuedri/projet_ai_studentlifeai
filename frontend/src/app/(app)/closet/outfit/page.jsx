"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Alert, Badge, Button, Card, EmptyState, Field, Input, Loading, PageHeader, Select, btnClass } from "@/components/ui";
import { api } from "@/lib/api";

export default function OutfitPage() {
  const [city, setCity] = useState("");
  const [style, setStyle] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async (seed) => {
    setLoading(true);
    setError("");
    const params = new URLSearchParams();
    if (city.trim()) params.set("city", city.trim());
    if (style) params.set("style", style);
    if (seed) params.set("seed", String(seed));
    try {
      setData(await api.get(`/closet/items/outfit/?${params}`));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [city, style]);

  // Chargement initial : la ville du profil est utilisée côté serveur si le champ est vide.
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const weather = data?.weather;
  return (
    <>
      <PageHeader title="Tenue du jour" subtitle="Une suggestion composée à partir de votre dressing et de la météo du moment." />

      <Card className="mb-6">
        <form onSubmit={(e) => { e.preventDefault(); load(); }} className="grid gap-4 sm:grid-cols-[1fr_200px_auto] sm:items-end">
          <Field label="Ville" hint="Vide : la ville de votre profil (ou Tunis) est utilisée.">
            <Input value={city} onChange={(e) => setCity(e.target.value)} placeholder={weather?.city || "Tunis"} />
          </Field>
          <Field label="Style">
            <Select value={style} onChange={(e) => setStyle(e.target.value)}>
              <option value="">Peu importe</option>
              <option>Casual</option><option>Formel</option><option>Sport</option>
            </Select>
          </Field>
          <div className="flex gap-2">
            <Button type="submit" loading={loading}>Voir la tenue</Button>
            <Button variant="secondary" disabled={loading || !data?.items.length} onClick={() => load(Date.now())}>Autre suggestion</Button>
          </div>
        </form>
      </Card>

      <Alert>{error}</Alert>
      {loading && !data && <Loading />}

      {data && (
        <div className={loading ? "opacity-60 transition-opacity" : "transition-opacity"}>
          <Card className="mb-6 flex flex-wrap items-center gap-x-8 gap-y-2">
            <div>
              <p className="text-4xl font-bold">{weather.temp}°C</p>
              <p className="text-sm text-slate-600">Ressenti {weather.feels_like}°C</p>
            </div>
            <div>
              <p className="font-medium">{weather.city}{weather.country && `, ${weather.country}`}</p>
              <p className="text-sm text-slate-600">{weather.description}</p>
            </div>
            {weather.rain && <Badge tone="blue">Pluie / précipitations</Badge>}
          </Card>

          {data.items.length === 0 ? (
            <EmptyState title="Pas encore de tenue à proposer"
              text="Ajoutez des vêtements à votre dressing (haut, bas, chaussures…) pour recevoir une suggestion."
              action={<Link href="/closet" className={btnClass("primary")}>Ouvrir mon dressing</Link>} />
          ) : (
            <>
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <h2 className="text-lg font-semibold">Ma suggestion</h2>
                <Badge tone="slate">Suggestion automatique</Badge>
              </div>
              <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4 lg:grid-cols-4">
                {data.items.map((item) => (
                  <li key={item.id}>
                    <Card className="overflow-hidden !p-0">
                      <img src={item.image} alt={`${item.item_type} ${item.color.toLowerCase()}`}
                        className="aspect-square w-full bg-brand-50 object-cover" />
                      <div className="p-3">
                        <p className="truncate font-medium">{item.name || item.item_type}</p>
                        <p className="text-sm text-slate-600">{item.color} · {item.style}</p>
                      </div>
                    </Card>
                  </li>
                ))}
              </ul>
            </>
          )}

          {data.advice.length > 0 && (
            <ul className="mt-5 space-y-1.5 text-sm text-slate-700">
              {data.advice.map((a) => <li key={a}>• {a}</li>)}
            </ul>
          )}
          {data.missing.length > 0 && (
            <div className="mt-5 space-y-2">
              {data.missing.map((m) => <Alert key={m} tone="info">{m}</Alert>)}
            </div>
          )}
          <p className="mt-6 text-xs text-slate-500">Cette tenue est une suggestion : vous restez libre de choisir autre chose.</p>
        </div>
      )}
    </>
  );
}
