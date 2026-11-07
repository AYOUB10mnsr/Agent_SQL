# Agent SQL — Assistant conversationnel pour Chinook

Assistant permettant d’interroger une base de données en français, sans connaître SQL ni les noms des tables.

Le projet utilise Gemini pour interpréter les questions, Python pour construire les requêtes autorisées et SQLite pour calculer les résultats.

> Prototype en développement : la conversation fonctionne dans le terminal. L’intégration LangGraph et l’interface web sont prévues.

## Objectif

Permettre à un utilisateur de poser des questions comme :

- « Combien de factures contient la base sur toute la période ? »
- « Quel est le montant total facturé en avril 2010 ? »
- « Quel est le montant facturé par pays en 2011 ? »
- « Et pour mai ? »

L’assistant demande une précision lorsque la question est ambiguë et conserve le contexte des échanges pendant la session.

## Fonctionnalités actuelles

- Interprétation des questions en français avec Gemini.
- Réponses structurées et vérifiées avec Pydantic.
- Clarification des informations manquantes.
- Mémoire conversationnelle pendant la session.
- Construction SQL à partir d’expressions prédéfinies.
- Exécution SQLite en lecture seule.
- Filtres sur les dates et le pays de facturation.
- Regroupement par mois ou pays de facturation.
- Affichage du SQL, des paramètres et des résultats.
- Quatre tests de calcul comparés à des résultats de référence.

### Indicateurs disponibles

| Indicateur | Définition |
|---|---|
| Montant facturé | Somme des montants des factures |
| Nombre de factures | Nombre de factures distinctes |
| Quantité vendue | Somme des quantités facturées |
| Montant des lignes | Somme des prix unitaires facturés multipliés par les quantités |
| Panier moyen | Montant moyen par facture |

Les montants sont manipulés en centièmes d’unité monétaire pour les sommes. La devise n’étant pas confirmée dans la configuration métier, aucun symbole monétaire n’est affiché.

## Fonctionnement

1. L’utilisateur saisit une question.
2. Python charge le schéma et les définitions métier.
3. Gemini produit une interprétation structurée.
4. Pydantic vérifie son format et certaines incohérences.
5. Si nécessaire, l’assistant demande une précision.
6. Python construit une requête à partir des indicateurs autorisés.
7. SQLite exécute le calcul.
8. Python présente les résultats.

### Rôle de Gemini

Gemini identifie :

- L’indicateur demandé.
- La période.
- Le regroupement.
- Le filtre géographique.
- Les informations manquantes.
- Les demandes hors périmètre.

Dans cette version, Gemini ne rédige pas directement le SQL et n’accède pas à la base. Il reçoit le schéma et le contexte métier ; lors des échanges suivants, il reçoit également l’historique, qui peut contenir les résultats agrégés précédemment affichés.

## Technologies

| Technologie | Utilisation |
|---|---|
| Python | Logique de l’application |
| SQLite | Base de données |
| Gemini API | Interprétation du langage naturel |
| Google Gen AI SDK | Communication avec Gemini |
| Pydantic | Validation des interprétations |
| python-dotenv | Lecture de la configuration |

## Données

Le projet utilise [Chinook](https://github.com/lerocha/chinook-database), une base exemple représentant un magasin de médias numériques.

La version utilisée contient notamment :

- 11 tables.
- 59 clients.
- 412 factures.
- 2 240 lignes de facture.
- 3 503 titres.

Les dates des factures vont du **1er janvier 2009 au 22 décembre 2013**.

Les données et les scripts Chinook proviennent du projet de Luis Rocha, distribué sous licence MIT. Consulter son dépôt pour les conditions d’utilisation et conserver les mentions de licence lors de leur redistribution.

## Structure du projet

```text
Agent SQL/
├── data/
│   └── Chinook_Sqlite.sqlite
├── knowledge/
│   ├── business_context.json
│   └── schema.json
├── evaluation/
│   ├── build_reference.py
│   ├── reference_cases.json
│   └── test_queries.py
├── chat_sql.py
├── export_schema.py
├── inspect_db.py
├── interpret_question.py
├── run_question.py
├── test_llm.py
├── .gitignore
└── README.md
```

Le fichier `.env` et l’environnement `.venv` sont locaux et doivent rester exclus de Git.

## Installation sous Windows

### 1. Récupérer le projet

Cloner le dépôt puis ouvrir son dossier dans VS Code.

### 2. Créer l’environnement Python

```powershell
python -m venv .venv
```

### 3. Installer les dépendances

```powershell
.\.venv\Scripts\python.exe -m pip install google-genai python-dotenv pydantic
```

### 4. Vérifier la présence de Chinook

La base doit se trouver ici :

```text
data/Chinook_Sqlite.sqlite
```

Si elle n’est pas présente, télécharger `Chinook_Sqlite.sqlite` depuis les [versions officielles de Chinook](https://github.com/lerocha/chinook-database/releases).

### 5. Configurer Gemini

Créer un fichier `.env` à la racine :

```dotenv
GEMINI_API_KEY=VOTRE_CLE_API
GEMINI_MODEL=MODELE_ACCESSIBLE_AVEC_VOTRE_COMPTE
```

Créer une clé depuis [Google AI Studio](https://aistudio.google.com/apikey).

Ne jamais publier la clé dans le dépôt. Les quotas, tarifs et conditions de traitement des données dépendent de l’offre utilisée.

### 6. Exporter le schéma si nécessaire

```powershell
.\.venv\Scripts\python.exe .\export_schema.py
```

Cette commande génère `knowledge/schema.json`.

### 7. Tester la connexion au modèle

```powershell
.\.venv\Scripts\python.exe .\test_llm.py
```

## Utilisation

Lancer la conversation :

```powershell
.\.venv\Scripts\python.exe .\chat_sql.py
```

Exemple :

```text
Toi : Quelles sont les ventes en avril ?

Assistant : De quelle année s'agit-il, et souhaitez-vous
connaître le montant ou la quantité ?

Toi : Le montant total facturé en 2010.

Assistant : Montant facturé
Période : du 2010-04-01 inclus au 2010-05-01 exclu.
Résultat : 37.62 unités monétaires

Toi : Et pour mai ?

Assistant : Montant facturé
Période : du 2010-05-01 inclus au 2010-06-01 exclu.
Résultat : 37.62 unités monétaires
```

### Commandes de conversation

| Commande | Action |
|---|---|
| `/reset` | Effacer le contexte |
| `/quit` | Quitter le programme |

Ces commandes doivent être saisies seules.

## Évaluation

### Construction des références

```powershell
.\.venv\Scripts\python.exe .\evaluation\build_reference.py
```

Le script compare des calculs SQL à des calculs Python réalisés sur les données brutes. Il enregistre les résultats attendus et une empreinte SHA-256 de la base.

Il vérifie également la correspondance entre les montants des factures et ceux de leurs lignes.

Les références doivent être revues avant d’être remplacées, notamment après une modification des données.

### Exécution des tests de calcul

```powershell
.\.venv\Scripts\python.exe .\evaluation\test_queries.py
```

Les quatre cas couvrent :

1. Le nombre total de factures.
2. Le montant total facturé.
3. La quantité totale vendue.
4. Les montants facturés par mois.

Résultat obtenu sur la base utilisée :

```text
Bilan : 4/4 tests réussis.
```

Ces tests n’appellent pas Gemini. Ils vérifient le constructeur SQL et les résultats, mais ne mesurent pas l’exactitude de l’interprétation des questions.

## Contrôles actuels

- Connexion SQLite en lecture seule.
- Activation de `PRAGMA query_only`.
- Indicateurs et regroupements limités à des valeurs autorisées.
- Valeurs de filtres transmises par paramètres SQL.
- Vérification de l’existence du pays de facturation demandé.
- Validation des dates et des champs structurés.
- Exclusion de la clé API du versionnement.

Ces contrôles ne garantissent pas la justesse de l’interprétation métier ni une sécurité complète pour une utilisation en production.

## Limites connues

- La mémoire disparaît à la fermeture du programme.
- Une demande ayant échoué lors de l’appel API n’est pas enregistrée.
- Les erreurs API 503 peuvent nécessiter de répéter la même question.
- Gemini peut sélectionner un mauvais indicateur malgré une sortie valide.
- Les classements, comparaisons et analyses causales ne sont pas encore pris en charge.
- Les marges, stocks et encaissements ne peuvent pas être calculés avec les données disponibles.
- Les périodes sans données et les mois sans facture nécessitent une interprétation prudente.
- Les quatre tests ne couvrent pas encore tous les indicateurs et filtres.
- L’authentification et les permissions par employé ne sont pas implémentées.
- LangGraph n’est pas encore intégré.

## Évolutions prévues

- Orchestration des étapes avec LangGraph.
- Gestion des délais d’attente et des nouvelles tentatives.
- Conservation de la demande en cours après une erreur API.
- Tests automatisés de compréhension et de conversation.
- Extension des tests aux périodes, pays et autres indicateurs.
- Interface Streamlit avec tableaux et graphiques.
- Journalisation des exécutions.
- Gestion des utilisateurs et de leurs droits.
