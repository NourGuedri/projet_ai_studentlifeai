"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { Alert, Badge, Button, Card, Field, Input, Select, Textarea } from "./ui";

let uid = 0;
const blank = () => ({ key: ++uid, text: "", choices: ["", "", "", ""], correct_index: 0, explanation: "", ai: false });

/** Create or edit a quiz: write questions by hand or generate them with AI, review, then save. */
export default function QuizEditor({ quiz, course, formation, formationId, onSaved }) {
  const [title, setTitle] = useState(quiz?.title ?? (course ? `Quiz : ${course.title}` : ""));
  const [questions, setQuestions] = useState(() =>
    (quiz?.questions ?? []).map((q) => ({
      key: ++uid, id: q.id, text: q.text, correct_index: q.correct_index, explanation: q.explanation || "", ai: false,
      choices: [...q.choices, ...Array(Math.max(0, 4 - q.choices.length)).fill("")],
    })),
  );
  const [source, setSource] = useState(course?.content ?? "");
  const [count, setCount] = useState(5);
  const [difficulty, setDifficulty] = useState("medium");
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const update = (key, patch) => setQuestions((qs) => qs.map((q) => (q.key === key ? { ...q, ...patch } : q)));

  async function generate() {
    setGenerating(true);
    setError("");
    try {
      const data = await api.post("/learning/quizzes/generate/", {
        text: source,
        ...(course?.id ? { course: course.id } : {}),
        ...(formationId ? { formation: formationId } : {}),
        num_questions: Number(count),
        difficulty,
      });
      setQuestions((qs) => [...qs, ...data.questions.map((q) => ({ ...q, key: ++uid, ai: true }))]);
    } catch (err) {
      setError(err.message);
    } finally {
      setGenerating(false);
    }
  }

  const hasFormationSources = formation?.lessons?.some((lesson) => lesson.content?.trim() || lesson.materials?.length);
  const canGenerate = source.trim().length >= 50 || !!course?.file || hasFormationSources;

  async function save(e) {
    e.preventDefault();
    setError("");
    if (questions.length === 0) return setError("Ajoutez au moins une question.");
    const payload = [];
    for (const [n, q] of questions.entries()) {
      const kept = q.choices.map((c, i) => ({ c: c.trim(), i })).filter((x) => x.c);
      const correct = kept.findIndex((x) => x.i === q.correct_index);
      if (!q.text.trim() || kept.length < 2) return setError(`Question ${n + 1} : saisissez l'énoncé et au moins deux choix.`);
      if (correct < 0) return setError(`Question ${n + 1} : la bonne réponse doit être un choix renseigné.`);
      payload.push({ ...(q.id ? { id: q.id } : {}), text: q.text.trim(), choices: kept.map((x) => x.c), correct_index: correct, explanation: q.explanation.trim() });
    }
    setSaving(true);
    try {
      const saved = quiz
        ? await api.patch(`/learning/quizzes/${quiz.id}/`, { title, questions: payload })
        : await api.post("/learning/quizzes/", {
            title, course: course?.id ?? null, formation: formationId ?? null,
            ai_generated: questions.some((q) => q.ai), questions: payload,
          });
      await onSaved(saved);
    } catch (err) {
      setError(err.message);
      setSaving(false);
    }
  }

  return (
    <form onSubmit={save} className="space-y-5">
      <Alert>{error}</Alert>
      <Field label="Titre du quiz"><Input required value={title} onChange={(e) => setTitle(e.target.value)} /></Field>

      <Card className="space-y-4">
        <div>
          <h2 className="text-lg font-semibold">Générer des questions avec l'IA</h2>
          <p className="text-sm text-slate-600">
            {formation
              ? "Les questions peuvent être générées à partir du contenu des leçons et de leurs documents PDF, DOCX, TXT ou MD. Vous pouvez aussi coller un texte. Vérifiez les questions avant d'enregistrer."
              : "Collez un texte ou générez à partir du document PDF, DOCX, TXT ou MD joint au cours. Vérifiez les questions avant de les enregistrer."}
            {" "}Les questions générées s'ajoutent à la suite.
          </p>
        </div>
        <Textarea rows={5} value={source} onChange={(e) => setSource(e.target.value)} placeholder="Texte de cours facultatif (50 caractères minimum)" />
        <div className="flex flex-wrap items-end gap-3">
          <Field label="Questions"><Select value={count} onChange={(e) => setCount(e.target.value)}>{[3, 5, 10, 15].map((n) => <option key={n}>{n}</option>)}</Select></Field>
          <Field label="Difficulté">
            <Select value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
              <option value="easy">Facile</option><option value="medium">Moyenne</option><option value="hard">Difficile</option>
            </Select>
          </Field>
          <Button variant="secondary" loading={generating} disabled={!canGenerate} onClick={generate}>Générer les questions</Button>
        </div>
      </Card>

      <div className="space-y-4">
        {questions.map((q, n) => (
          <Card key={q.key} className="space-y-3">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <h3 className="font-semibold">Question {n + 1}</h3>
                {q.ai && <Badge tone="blue">Générée par l'IA</Badge>}
              </div>
              <Button size="sm" variant="danger" onClick={() => setQuestions((qs) => qs.filter((x) => x.key !== q.key))}>Retirer</Button>
            </div>
            <Textarea rows={2} required value={q.text} onChange={(e) => update(q.key, { text: e.target.value })} placeholder="Énoncé de la question" />
            <fieldset className="space-y-2">
              <legend className="mb-1 text-sm font-medium">Choix (cochez la bonne réponse)</legend>
              {q.choices.map((c, i) => (
                <div key={i} className="flex items-center gap-3">
                  <input type="radio" name={`correct-${q.key}`} checked={q.correct_index === i} onChange={() => update(q.key, { correct_index: i })} className="h-4 w-4 accent-leaf-600" aria-label={`Choix ${i + 1} correct`} />
                  <Input value={c} placeholder={`Choix ${i + 1}`} onChange={(e) => update(q.key, { choices: q.choices.map((x, j) => (j === i ? e.target.value : x)) })} />
                </div>
              ))}
            </fieldset>
            <Input value={q.explanation} onChange={(e) => update(q.key, { explanation: e.target.value })} placeholder="Explication affichée après la réponse (facultatif)" />
          </Card>
        ))}
        <Button variant="secondary" onClick={() => setQuestions((qs) => [...qs, blank()])}>Ajouter une question</Button>
      </div>

      <div className="border-t border-brand-100 pt-5">
        <Button type="submit" variant="success" loading={saving}>{quiz ? "Enregistrer les modifications" : "Enregistrer le quiz"}</Button>
      </div>
    </form>
  );
}
