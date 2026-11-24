"use client";
import { useCallback, useEffect, useState } from "react";
import { Alert, Badge, Button, Card, EmptyState, Field, Input, Loading, PageHeader, Select, Textarea } from "@/components/ui";
import { api } from "@/lib/api";

const fmt = (iso) =>
  new Date(iso).toLocaleString("fr-FR", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

// datetime-local attend "AAAA-MM-JJTHH:MM" en heure locale
const localInput = (date) => {
  const d = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return d.toISOString().slice(0, 16);
};

const EMPTY_TRIP = { departure: "", destination: "", departure_time: "", mode: "bus", line: "", seats_available: 0 };

/* ------------------------------------------------------------ US 35 : mes trajets */
function TripForm({ options, onSaved }) {
  const [trip, setTrip] = useState({ ...EMPTY_TRIP, departure_time: localInput(new Date(Date.now() + 3600000)) });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const set = (key) => (e) => setTrip({ ...trip, [key]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      await api.post("/transport/trips/", {
        ...trip,
        departure_time: new Date(trip.departure_time).toISOString(),
        seats_available: trip.mode === "voiture" ? Number(trip.seats_available) || 0 : 0,
      });
      setTrip({ ...EMPTY_TRIP, departure_time: trip.departure_time, mode: trip.mode });
      onSaved();
    } catch (err) { setError(err.message); }
    finally { setSaving(false); }
  }

  return (
    <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
      <Field label="Départ"><Input required maxLength={120} value={trip.departure} onChange={set("departure")} placeholder="Ex. Ariana" /></Field>
      <Field label="Destination"><Input required maxLength={120} value={trip.destination} onChange={set("destination")} placeholder="Ex. TEK-UP" /></Field>
      <Field label="Heure de départ"><Input required type="datetime-local" value={trip.departure_time} onChange={set("departure_time")} /></Field>
      <Field label="Moyen de transport">
        <Select value={trip.mode} onChange={set("mode")}>
          {options.modes.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
        </Select>
      </Field>
      <Field label="Ligne (facultatif)" hint="Les alertes d'une ligne précise ne concernent que cette ligne.">
        <Input maxLength={30} value={trip.line} onChange={set("line")} placeholder="Ex. Ligne 4, TGM" />
      </Field>
      {trip.mode === "voiture" && (
        <Field label="Places proposées aux autres étudiants" hint="0 si vous ne faites pas de covoiturage.">
          <Input type="number" min={0} max={8} value={trip.seats_available} onChange={set("seats_available")} />
        </Field>
      )}
      <div className="sm:col-span-2 flex flex-col gap-2">
        <Alert>{error}</Alert>
        <div><Button type="submit" loading={saving}>Ajouter le trajet</Button></div>
      </div>
    </form>
  );
}

function TripList({ trips, onDelete }) {
  if (!trips) return <Loading />;
  if (trips.length === 0) {
    return <EmptyState title="Aucun trajet à venir"
      text="Ajoutez vos trajets : vous serez prévenu si un incident risque de vous retarder." />;
  }
  return (
    <ul className="divide-y divide-brand-50">
      {trips.map((t) => (
        <li key={t.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
          <div className="min-w-0">
            <p className="font-medium">{t.departure} → {t.destination}</p>
            <p className="text-sm text-slate-600">{fmt(t.departure_time)}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge>{t.mode_label}{t.line ? ` · ${t.line}` : ""}</Badge>
            {t.seats_available > 0 && <Badge tone="green">{t.seats_available} place(s) proposée(s)</Badge>}
            <Button size="sm" variant="danger" onClick={() => onDelete(t)}>Supprimer</Button>
          </div>
        </li>
      ))}
    </ul>
  );
}

/* ------------------------------------------------------------ US 36 : incidents et estimation ML */
function Prediction({ result, threshold }) {
  if (!result) return null;
  const pct = Math.round(result.long_delay_probability * 100);
  return (
    <div className={`rounded-lg border p-4 ${result.is_long_delay ? "border-amber-200 bg-amber-50" : "border-leaf-100 bg-leaf-50"}`}>
      <p className="font-display text-lg font-semibold">
        Retard estimé : environ {result.estimated_delay_min} min
      </p>
      <p className="mt-1 text-sm">
        Risque de retard de plus de 15 min : <strong>{pct} %</strong>{" "}
        {result.is_long_delay
          ? <Badge tone="amber">Alerte : risque de retard long</Badge>
          : <Badge tone="green">Risque faible</Badge>}
      </p>
      {result.notified_count !== undefined && (
        <p className="mt-2 text-sm text-slate-700">
          {result.is_long_delay
            ? `${result.notified_count} étudiant(s) concerné(s) prévenu(s).`
            : "Aucune alerte envoyée."}
        </p>
      )}
      <p className="mt-2 text-xs text-slate-500">
        Estimation automatique par un modèle de Machine Learning : elle peut se tromper.
        L'alerte se déclenche dès {Math.round(threshold * 100)} % de risque, pour rater le moins possible de retards longs.
      </p>
    </div>
  );
}

function IncidentForm({ options, onReported }) {
  const [incident, setIncident] = useState({ mode: "bus", incident_type: "MECHANICAL", line: "", description: "" });
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const choices = options.incidents[incident.mode] || [];

  function setMode(e) {
    const mode = e.target.value;
    setIncident({ ...incident, mode, incident_type: options.incidents[mode][0].value });
    setResult(null);
  }
  const set = (key) => (e) => { setIncident({ ...incident, [key]: e.target.value }); setResult(null); };

  async function run(kind) {
    setBusy(kind);
    setError("");
    try {
      if (kind === "estimate") {
        setResult(await api.post("/transport/predict/", { mode: incident.mode, incident_type: incident.incident_type }));
      } else {
        const data = await api.post("/transport/incidents/", incident);
        if (data.prediction_error) setError(`Incident enregistré, mais ${data.prediction_error}`);
        setResult(data.estimated_delay_min === null ? null : data);
        onReported();
      }
    } catch (err) { setError(err.message); }
    finally { setBusy(""); }
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <Field label="Moyen de transport">
        <Select value={incident.mode} onChange={setMode}>
          {options.modes.filter((m) => options.predictable_modes.includes(m.value))
            .map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
        </Select>
      </Field>
      <Field label="Type d'incident">
        <Select value={incident.incident_type} onChange={set("incident_type")}>
          {choices.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
        </Select>
      </Field>
      <Field label="Ligne (facultatif)"><Input maxLength={30} value={incident.line} onChange={set("line")} placeholder="Ex. Ligne 4" /></Field>
      <Field label="Détails (facultatif)"><Textarea rows={1} value={incident.description} onChange={set("description")} /></Field>
      <div className="sm:col-span-2 flex flex-col gap-3">
        <Alert>{error}</Alert>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" loading={busy === "estimate"} disabled={!!busy} onClick={() => run("estimate")}>Estimer le retard</Button>
          <Button loading={busy === "report"} disabled={!!busy} onClick={() => run("report")}>Signaler l'incident</Button>
        </div>
        <Prediction result={result} threshold={options.model?.threshold} />
      </div>
    </div>
  );
}

function ModelCard({ model }) {
  if (!model) {
    return <Alert tone="info">Les modèles de prédiction ne sont pas disponibles sur ce serveur : les trajets fonctionnent, mais sans estimation de retard.</Alert>;
  }
  const r = model.regression, c = model.classification;
  return (
    <div className="space-y-2 text-sm text-slate-700">
      <p>
        Deux modèles entraînés sur {model.n_rows.toLocaleString("fr-FR")} incidents réels :
        <strong> {r.model}</strong> estime les minutes de retard (erreur moyenne ≈ {r.mae.toFixed(1)} min, R² = {r.r2.toFixed(2)}),
        <strong> {c.model}</strong> prédit un retard de plus de {model.long_delay_minutes} min
        (Recall = {Math.round(c.recall * 100)} %, F1 = {c.f1.toFixed(2)}, AUC = {c.auc.toFixed(2)}, seuil = {model.threshold}).
      </p>
      <p className="text-xs text-slate-500">
        Limite : les données proviennent du réseau de Toronto (TTC Delay Data 2024), faute de données ouvertes équivalentes pour Tunis.
        Contains information licensed under the Open Government Licence – Toronto.
      </p>
    </div>
  );
}

/* ------------------------------------------------------------ page */
export default function TransportPage() {
  const [options, setOptions] = useState(null);
  const [trips, setTrips] = useState(null);
  const [incidents, setIncidents] = useState(null);
  const [carpool, setCarpool] = useState(null);
  const [error, setError] = useState("");

  const loadTrips = useCallback(() => api.get("/transport/trips/?upcoming=1").then(setTrips).catch((e) => setError(e.message)), []);
  const loadIncidents = useCallback(() => api.get("/transport/incidents/").then(setIncidents).catch((e) => setError(e.message)), []);

  useEffect(() => {
    api.get("/transport/options/").then(setOptions).catch((e) => setError(e.message));
    api.get("/transport/trips/carpool/").then(setCarpool).catch((e) => setError(e.message));
    loadTrips();
    loadIncidents();
  }, [loadTrips, loadIncidents]);

  async function removeTrip(trip) {
    if (!confirm(`Supprimer le trajet ${trip.departure} → ${trip.destination} ?`)) return;
    try { await api.del(`/transport/trips/${trip.id}/`); await loadTrips(); }
    catch (err) { setError(err.message); }
  }

  if (!options) return error ? <Alert>{error}</Alert> : <Loading />;

  return (
    <>
      <PageHeader title="Transport"
        subtitle="Renseignez vos trajets. Quand un incident est signalé, l'IA estime le retard et vous prévient s'il risque de dépasser 15 minutes." />
      <Alert>{error}</Alert>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <h2 className="mb-4 text-lg font-semibold">Ajouter un trajet</h2>
          <TripForm options={options} onSaved={loadTrips} />
        </Card>
        <Card>
          <h2 className="mb-2 text-lg font-semibold">Mes prochains trajets</h2>
          <TripList trips={trips} onDelete={removeTrip} />
        </Card>

        <Card>
          <h2 className="mb-1 text-lg font-semibold">Signaler un incident</h2>
          <p className="mb-4 text-sm text-slate-600">
            Les étudiants qui partent dans les {options.alert_window_hours} prochaines heures avec ce moyen de transport seront prévenus si le retard s'annonce long.
          </p>
          <IncidentForm options={options} onReported={loadIncidents} />
        </Card>
        <Card>
          <h2 className="mb-2 text-lg font-semibold">Incidents récents</h2>
          {!incidents ? <Loading /> : incidents.length === 0 ? (
            <p className="text-sm text-slate-600">Aucun incident signalé ces 7 derniers jours.</p>
          ) : (
            <ul className="divide-y divide-brand-50">
              {incidents.slice(0, 8).map((i) => (
                <li key={i.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
                  <div className="min-w-0">
                    <p className="font-medium">{i.incident_label} · {i.mode_label}{i.line ? ` ${i.line}` : ""}</p>
                    <p className="text-sm text-slate-600">{fmt(i.occurred_at)}</p>
                  </div>
                  {i.estimated_delay_min === null ? <Badge tone="slate">Sans estimation</Badge>
                    : <Badge tone={i.is_long_delay ? "amber" : "green"}>≈ {i.estimated_delay_min} min</Badge>}
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card>
          <h2 className="mb-2 text-lg font-semibold">Covoiturage proposé</h2>
          {!carpool ? <Loading /> : carpool.length === 0 ? (
            <p className="text-sm text-slate-600">Aucune place de voiture proposée pour le moment.</p>
          ) : (
            <ul className="divide-y divide-brand-50">
              {carpool.map((t) => (
                <li key={t.id} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
                  <div className="min-w-0">
                    <p className="font-medium">{t.departure} → {t.destination}</p>
                    <p className="text-sm text-slate-600">{fmt(t.departure_time)} · {t.driver}</p>
                  </div>
                  <Badge tone="green">{t.seats_available} place(s)</Badge>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card>
          <h2 className="mb-2 text-lg font-semibold">Comment l'IA estime le retard</h2>
          <ModelCard model={options.model} />
        </Card>
      </div>
    </>
  );
}