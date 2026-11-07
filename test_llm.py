from pathlib import Path

from dotenv import dotenv_values
from google import genai

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"

if not ENV_PATH.is_file():
    raise FileNotFoundError(f"Fichier introuvable : {ENV_PATH}")

# Lecture directe du fichier, sans utiliser les variables du terminal.
config = dotenv_values(ENV_PATH, encoding="utf-8-sig")

api_key = (config.get("GEMINI_API_KEY") or "").strip()
model_name = (config.get("GEMINI_MODEL") or "").strip()

if not api_key or api_key.startswith("COLLE_"):
    raise ValueError("La clé est absente ou contient le texte d'exemple.")

if not model_name:
    raise ValueError("GEMINI_MODEL est absent du fichier .env.")

print("Configuration chargée. Test de connexion…")

with genai.Client(api_key=api_key) as client:
    response = client.models.generate_content(
        model=model_name,
        contents=(
            "Réponds en français, en une seule phrase : "
            "quel est le rôle d'un assistant Text-to-SQL ?"
        ),
    )

    print(response.text or "Réponse reçue sans texte exploitable.")