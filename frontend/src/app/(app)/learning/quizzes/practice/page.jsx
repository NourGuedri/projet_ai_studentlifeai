"use client";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Alert, Badge, Button, Card, Field, Loading, PageHeader, ProgressBar, ScoreRing, Select, Textarea, cx } from "@/components/ui";
import { api } from "@/lib/api";

function PracticeQuiz() {
  const params = useSearchParams();
  const courseId = params.get("course");
  const [course, setCourse] = useState(null);
  const [source, setSource] = useState("");
  const [count, setCount] = useState(5);
  const [difficulty, setDifficulty] = useState("medium");
  const [questions, setQuestions] = useState(null);
  const [answers, setAnswers] = useState({});
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!courseId) return;
    api.get(`/learning/courses/${courseId}/`)
      .then((data) => { setCourse(data); setSource(data.content); })
      .catch((err) => setError(err.message));
  }, [courseId]);

  async function generate() {
    setBusy(true);
    setError("");
    setQuestions(null);
    setAnswers({});
    setResult(null);
    try {
      const data = await api.post("/learning/quizzes/generate/", {
        text: source,
        ...(courseId ? { course: Number(courseId) } : {}),
        num_questions: Number(count),
        difficulty,
      });
      setQuestions(data.questions);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function submit() {
    const results = questions.map((question, index) => {
      const chosen = answers[index] ?? null;
      return {
        chosen,
        correct_index: question.correct_index,
        correct: chosen === question.correct_index,
        explanation: question.explanation,
      };
    });
    const score = results.filter((answer) => answer.correct).length;
    setResult({
      score,
      total: questions.length,
      percent: Math.round((100 * score) / questions.length),
      results,
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function retry() {
    setAnswers({});
    setResult(null);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  const answered = Object.keys(answers).length;

  return (
    <>
      <PageHeader
        title="Quiz d'entraînement avec l'IA"
        subtitle={course ? `À partir du cours « ${course.title} » et de son document joint` : "Générez un quiz privé pour vous entraîner. Il ne sera pas enregistré."}
      />
      <div className="mb-4"><Alert>{error}</Alert></div>

      {!questions && (
        <Card className="mb-6 space-y-4">
          <p className="text-sm text-slate-600">Collez un texte de cours ou utilisez le document PDF, DOCX, TXT ou MD joint à votre cours. Choisissez les options, puis lancez la génération. Vous pourrez répondre et consulter la correction sans enregistrer le quiz.</p>
          <Textarea rows={8} value={source} onChange={(event) => setSource(event.target.value)} placeholder="Texte de cours (50 caractères minimum)" />
          <div className="flex flex-wrap items-end gap-3">
            <Field label="Questions">
              <Select value={count} onChange={(event) => setCount(event.target.value)}>{[3, 5, 10, 15].map((number) => <option key={number}>{number}</option>)}</Select>
            </Field>
            <Field label="Difficulté">
              <Select value={difficulty} onChange={(event) => setDifficulty(event.target.value)}>
                <option value="easy">Facile</option><option value="medium">Moyenne</option><option value="hard">Difficile</option>
              </Select>
            </Field>
            <Button variant="success" loading={busy} disabled={source.trim().length < 50 && !course?.file} onClick={generate}>Générer et commencer</Button>
          </div>
        </Card>
      )}

      {questions && (
        <>
          <div className="mb-4 flex items-center justify-between gap-3">
            <Badge tone="slate">Quiz privé — non enregistré</Badge>
            <Button variant="secondary" size="sm" onClick={() => { setQuestions(null); setResult(null); }}>Générer un autre quiz</Button>
          </div>

          {result ? (
            <Card className="mb-6 flex flex-col items-center gap-4 text-center sm:flex-row sm:text-left">
              <ScoreRing percent={result.percent} />
              <div className="flex-1">
                <p className="font-display text-xl font-semibold">{result.score} bonnes réponses sur {result.total}</p>
                <p className="mt-1 text-sm text-slate-600">
                  {result.percent >= 80 ? "Très bien, continuez ainsi !" : result.percent >= 60 ? "Bon travail, relisez les explications ci-dessous." : "Relisez le cours et réessayez."}
                </p>
                <div className="mt-3"><Button variant="success" onClick={retry}>Refaire le quiz</Button></div>
              </div>
            </Card>
          ) : (
            <div className="sticky top-14 z-20 -mx-4 mb-5 border-b border-brand-100 bg-mist/95 px-4 py-3 backdrop-blur sm:mx-0 sm:rounded-lg sm:border lg:top-2">
              <div className="mb-1 flex justify-between text-sm"><span>{answered} / {questions.length} réponses</span></div>
              <ProgressBar value={(100 * answered) / questions.length} />
            </div>
          )}

          <ol className="space-y-5">
            {questions.map((question, index) => {
              const answer = result?.results[index];
              return (
                <li key={index}>
                  <Card>
                    <p className="font-medium"><span className="text-brand-600">{index + 1}.</span> {question.text}</p>
                    <div className="mt-3 space-y-2" role="radiogroup">
                      {question.choices.map((choice, choiceIndex) => {
                        const isCorrect = answer && choiceIndex === answer.correct_index;
                        const isWrong = answer && answer.chosen === choiceIndex && !answer.correct;
                        return (
                          <label key={choiceIndex} className={cx(
                            "flex min-h-11 items-center gap-3 rounded-lg border px-3 py-2.5 text-sm transition-colors",
                            answer ? "cursor-default" : "cursor-pointer hover:bg-brand-50 has-[:checked]:border-brand-600 has-[:checked]:bg-brand-50",
                            isCorrect ? "border-leaf-500 bg-leaf-50" : isWrong ? "border-red-300 bg-red-50" : !answer && "border-brand-200",
                            answer && !isCorrect && !isWrong && "border-brand-100 text-slate-500",
                          )}>
                            <input
                              type="radio"
                              name={`question-${index}`}
                              disabled={!!answer}
                              checked={answers[index] === choiceIndex}
                              onChange={() => setAnswers({ ...answers, [index]: choiceIndex })}
                              className="h-4 w-4 accent-brand-600"
                            />
                            <span className="flex-1">{choice}</span>
                            {isCorrect && <Badge tone="green">Bonne réponse</Badge>}
                            {isWrong && <Badge tone="red">Votre réponse</Badge>}
                          </label>
                        );
                      })}
                    </div>
                    {answer?.explanation && <p className="mt-3 rounded-lg bg-brand-50 px-3 py-2 text-sm text-slate-700">{answer.explanation}</p>}
                  </Card>
                </li>
              );
            })}
          </ol>

          {!result && (
            <div className="mt-6">
              <Button variant="success" disabled={answered === 0} onClick={submit}>Corriger mes réponses</Button>
              {answered > 0 && answered < questions.length && <p className="mt-2 text-sm text-slate-600">Les questions sans réponse comptent comme fausses.</p>}
            </div>
          )}
        </>
      )}
    </>
  );
}

export default function PracticeQuizPage() {
  return <Suspense fallback={<Loading />}><PracticeQuiz /></Suspense>;
}
