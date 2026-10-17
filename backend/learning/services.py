from common import ai

PROMPT = """Tu es un enseignant. À partir du texte de cours ci-dessous, crée {n} questions à choix multiples de difficulté « {difficulty} ».
Règles : rédige dans la même langue que le cours ; exactement 4 choix par question ; une seule bonne réponse ; une courte explication ; n'utilise que des informations présentes dans le texte.
Réponds uniquement avec un tableau JSON de la forme :
[{{"text": "...", "choices": ["...", "...", "...", "..."], "correct_index": 0, "explanation": "..."}}]

CONTENU DU COURS ET DES DOCUMENTS FOURNIS :
{text}
"""


def generate_questions(text, n=5, difficulty="medium"):
    data = ai.generate_json(PROMPT.format(n=n, difficulty=difficulty, text=text[:40000]))
    if isinstance(data, dict):
        data = data.get("questions", [])
    questions = []
    for item in data if isinstance(data, list) else []:
        try:
            choices = [str(c).strip() for c in item["choices"] if str(c).strip()]
            index = int(item["correct_index"])
            text_q = str(item["text"]).strip()
        except (KeyError, TypeError, ValueError):
            continue
        if text_q and len(choices) >= 2 and 0 <= index < len(choices):
            questions.append({
                "text": text_q, "choices": choices, "correct_index": index,
                "explanation": str(item.get("explanation", "")).strip(),
            })
    if not questions:
        raise ai.AIError("L'IA n'a produit aucune question exploitable. Réessayez.")
    return questions[:n]
