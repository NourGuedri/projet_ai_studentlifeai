"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Alert, Badge, Button, Card, Loading, PageHeader, ProgressBar, ScoreRing, btnClass, cx } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function QuizPage() {
  const { user } = useAuth();
  const { id } = useParams();
  const router = useRouter();
  const [quiz, setQuiz] = useState(null);
  const [answers, setAnswers] = useState({});
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { api.get(`/learning/quizzes/${id}/`).then(setQuiz).catch((e) => setError(e.message)); }, [id]);

  async function submit() {
    setBusy(true);
    setError("");
    try {
      setResult(await api.post(`/learning/quizzes/${id}/submit/`, { answers }));
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  async function remove() {
    if (!confirm("Supprimer ce quiz et ses résultats ?")) return;
    await api.del(`/learning/quizzes/${id}/`);
    router.replace("/learning/quizzes");
  }

  function retry() { setAnswers({}); setResult(null); window.scrollTo({ top: 0 }); }

  if (error && !quiz) return <Alert>{error}</Alert>;
  if (!quiz) return <Loading />;
  const isTeacher = user.role === "teacher" || user.role === "admin";
  const answered = Object.keys(answers).length;
  const byId = result ? Object.fromEntries(result.results.map((r) => [r.question_id, r])) : {};

  return (
    <>
      <PageHeader title={quiz.title}
        subtitle={`${quiz.question_count} questions`}
        actions={isTeacher && quiz.is_owner && (
          <>
            <Link href={`/learning/quizzes/${id}/edit`} className={btnClass("secondary", "sm")}>Modifier le quiz</Link>
            <Button variant="danger" size="sm" onClick={remove}>Supprimer le quiz</Button>
          </>
        )} />
      {quiz.ai_generated && <div className="-mt-3 mb-4"><Badge tone="slate">Questions générées par l'IA</Badge></div>}
      <div className="mb-4"><Alert>{error}</Alert></div>

      {result && !isTeacher ? (
        <Card className="mb-6 flex flex-col items-center gap-4 text-center sm:flex-row sm:text-left">
          <ScoreRing percent={result.percent} />
          <div className="flex-1">
            <p className="font-display text-xl font-semibold">{result.score} bonnes réponses sur {result.total}</p>
            <p className="mt-1 text-sm text-slate-600">
              {result.percent >= 80 ? "Très bien, ce cours est solide." : result.percent >= 60 ? "Pas mal, relisez les explications ci-dessous." : "Ce cours mérite une nouvelle révision."}
            </p>
            <div className="mt-3 flex flex-wrap justify-center gap-2 sm:justify-start">
              <Button variant="success" onClick={retry}>Refaire le quiz</Button>
              <Link href="/learning/results" className={btnClass("secondary")}>Voir mes résultats</Link>
            </div>
          </div>
        </Card>
      ) : !isTeacher ? (
        <div className="sticky top-14 z-20 -mx-4 mb-5 border-b border-brand-100 bg-mist/95 px-4 py-3 backdrop-blur sm:mx-0 sm:rounded-lg sm:border lg:top-2">
          <div className="mb-1 flex justify-between text-sm"><span>{answered} / {quiz.questions.length} réponses</span></div>
          <ProgressBar value={(100 * answered) / quiz.questions.length} />
        </div>
      ) : <p className="mb-5 rounded-lg bg-brand-50 px-3 py-2 text-sm text-brand-700">Mode consultation : les formateurs ne passent pas les quiz.</p>}

      <ol className="space-y-5">
        {quiz.questions.map((q, n) => {
          const r = byId[q.id];
          const isCorrectAnswer = isTeacher && q.correct_index !== undefined;
          return (
            <li key={q.id}>
              <Card>
                <p className="font-medium"><span className="text-brand-600">{n + 1}.</span> {q.text}</p>
                <div className="mt-3 space-y-2" role="radiogroup">
                  {q.choices.map((choice, i) => {
                    const isCorrect = (r && i === r.correct_index) || (isCorrectAnswer && i === q.correct_index);
                    const isWrong = r && r.chosen === i && !r.correct;
                    return (
                      <label key={i} className={cx(
                        "flex min-h-11 items-center gap-3 rounded-lg border px-3 py-2.5 text-sm transition-colors",
                        r ? "cursor-default" : !isTeacher && "cursor-pointer hover:bg-brand-50 has-[:checked]:border-brand-600 has-[:checked]:bg-brand-50",
                        isCorrect ? "border-leaf-500 bg-leaf-50" : isWrong ? "border-red-300 bg-red-50" : !r && "border-brand-200",
                        r && !isCorrect && !isWrong && "border-brand-100 text-slate-500")}>
                        {!isTeacher && <input type="radio" name={`q-${q.id}`} disabled={!!r} checked={answers[q.id] === i}
                          onChange={() => setAnswers({ ...answers, [q.id]: i })} className="h-4 w-4 accent-brand-600" />}
                        <span className="flex-1">{choice}</span>
                        {isCorrect && <Badge tone="green">{isTeacher ? "Réponse correcte" : "Bonne réponse"}</Badge>}
                        {isWrong && <Badge tone="red">Votre réponse</Badge>}
                      </label>
                    );
                  })}
                </div>
                {(r?.explanation || (isTeacher && q.explanation)) && <p className="mt-3 rounded-lg bg-brand-50 px-3 py-2 text-sm text-slate-700">{r?.explanation || q.explanation}</p>}
              </Card>
            </li>
          );
        })}
      </ol>

      {!isTeacher && !result && (
        <div className="mt-6">
          <Button variant="success" loading={busy} disabled={answered === 0} onClick={submit}>Valider mes réponses</Button>
          {answered > 0 && answered < quiz.questions.length && <p className="mt-2 text-sm text-slate-600">Les questions sans réponse comptent comme fausses.</p>}
        </div>
      )}
    </>
  );
}
