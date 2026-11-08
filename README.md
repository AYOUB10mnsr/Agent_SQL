# Agent SQL — Assistant conversationnel pour Chinook

Application permettant d’interroger une base de données en français, sans connaître SQL ni les noms des tables.

Gemini interprète les questions et génère des propositions SQL. Python vérifie les requêtes, contrôle les périodes prises en charge et pilote leur exécution en lecture seule dans SQLite.

Les résultats sont accessibles dans une interface Streamlit ou depuis le terminal.

> Prototype fonctionnel en développement. Les contrôles techniques ne garantissent pas, à eux seuls, la justesse métier des réponses.

## Objectif

Permettre à un utilisateur de poser des questions comme :

- « Quel est le montant total facturé en avril 2010 ? »
- « Quels sont les cinq clients ayant le montant total facturé le plus élevé en 2010 ? »
- « Quel est le montant vendu par genre musical en 2011 ? »
- « Et en 2011 ? »
- « Et les dix premiers ? »

L’assistant peut demander des précisions et utiliser les échanges précédents pour comprendre les questions de suivi.

## Fonctionnalités actuelles

### Conversation

- Questions en français.
- Clarification des demandes ambiguës.
- Conservation du contexte pendant la session.
- Modification progressive des critères : année, mois, pays ou taille d’un classement.
- Conservation de la question en attente après un échec.
- Reprise manuelle ou abandon de cette question.

### Génération et calcul

- Génération SQL par Gemini à partir du schéma et des définitions métier.
- Agrégations, jointures, classements et sous-requêtes selon les restrictions du validateur.
- Paramètres SQL nommés pour les valeurs de filtrage.
- Validation technique avant chaque exécution.
- Connexion SQLite en lecture seule.
- Contrôle des périodes temporelles prises en charge.
- Interruption périodique des calculs dépassant le délai configuré.
- Affichage plafonné à 100 lignes.

### Interface

- Conversation dans le navigateur avec Streamlit.
- Résultats présentés dans des tableaux.
- Affichage des hypothèses et avertissements.
- SQL et paramètres consultables dans un volet dépliable.
- Temps de réponse affiché.
- Boutons pour recommencer une conversation, réessayer ou abandonner une demande.

## Architecture actuelle

Le parcours principal est le suivant :

1. L’utilisateur saisit une question.
2. Python charge le schéma et le contexte métier.
3. Gemini renvoie une proposition structurée :
   - demande de clarification ;
   - demande non prise en charge ;
   - requête SQL proposée et paramètres.
4. Pydantic vérifie la structure de la proposition.
5. SQLGlot analyse le SQL.
6. SQLite prépare le plan avec `EXPLAIN QUERY PLAN`, sans calculer les résultats.
7. Le contrôle des dates examine les filtres temporels pris en charge.
8. Une connexion contrôlée exécute la requête.
9. Python présente les résultats et mémorise l’échange terminé.

### Rôle de Gemini

Gemini intervient pour :

- Comprendre la question et le contexte conversationnel.
- Identifier les informations manquantes.
- Générer le SQL et ses paramètres.
- Expliquer le calcul proposé.
- Signaler certaines hypothèses ou limites.

Gemini ne possède pas de connexion directe à SQLite. Les chiffres affichés proviennent de l’exécution SQL, pas d’un calcul réalisé par le modèle.

Le modèle reçoit le schéma, les définitions métier et l’historique utile. Cet historique peut contenir les résultats précédemment affichés.

### Deux parcours conservés

| Parcours | Fonctionnement |
|---|---|
| Initial | Gemini sélectionne un indicateur ; Python construit une requête prédéfinie |
| Exploratoire | Gemini génère le SQL ; Python le valide et pilote son exécution |

L’interface Streamlit utilise le parcours exploratoire.

LangGraph n’est pas nécessaire au lancement de ce parcours. Une orchestration plus élaborée reste une évolution possible.

## Technologies

| Technologie | Utilisation |
|---|---|
| Python | Logique applicative |
| SQLite | Stockage et calcul |
| Gemini API | Interprétation et génération SQL |
| Google Gen AI SDK | Communication avec le modèle |
| Pydantic | Validation des sorties structurées |
| SQLGlot | Analyse de la structure SQL |
| Streamlit | Interface conversationnelle |
| pandas | Présentation des résultats en tableaux |
| python-dotenv | Lecture de la configuration locale |

## Données

Le projet utilise [Chinook](https://github.com/lerocha/chinook-database), une base exemple représentant un magasin de médias numériques.

La version utilisée contient notamment :

| Élément | Nombre |
|---|---:|
| Tables | 11 |
| Clients | 59 |
| Factures | 412 |
| Lignes de facture | 2 240 |
| Titres du catalogue | 3 503 |

Les dates des factures présentes vont du **1er janvier 2009 au 22 décembre 2013**.

Ces dates extrêmes ne garantissent pas que les données sont complètes pour tous les jours de l’intervalle.

Les données et scripts Chinook proviennent du projet de Luis Rocha, distribué sous licence MIT. Conserver les mentions de licence applicables lors de leur redistribution.

## Définitions métier

Le fichier `knowledge/business_context.json` décrit les indicateurs et les règles de calcul.

| Indicateur | Définition |
|---|---|
| Montant facturé | Somme des montants des factures |
| Nombre de factures | Nombre de factures distinctes |
| Quantité vendue | Somme des quantités facturées |
| Montant des lignes | Somme des prix unitaires facturés multipliés par les quantités |
| Panier moyen | Montant moyen par facture |

Règles principales :

- Utiliser `Invoice.InvoiceDate` pour dater les ventes.
- Utiliser `Invoice.BillingCountry` pour le pays de facturation.
- Utiliser `InvoiceLine.UnitPrice` pour le prix historique de vente.
- Éviter de compter plusieurs fois une facture après une jointure avec ses lignes.
- Calculer les ventes par titre ou genre à partir des lignes de facture.
- Privilégier les centièmes entiers pour les sommes monétaires.

La devise n’étant pas confirmée, aucun symbole monétaire n’est imposé.

Les règles données au modèle restent des instructions : leur respect doit être évalué.

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
├── app.py
├── generate_sql.py
├── validate_sql.py
├── date_guard.py
├── execute_generated.py
├── chat_exploratory.py
├── chat_reliable.py
├── chat_sql.py
├── interpret_question.py
├── run_question.py
├── export_schema.py
├── inspect_db.py
├── test_llm.py
├── .gitignore
└── README.md
```

### Principaux fichiers

| Fichier | Responsabilité |
|---|---|
| `app.py` | Interface Streamlit |
| `generate_sql.py` | Génération SQL et clarification avec historique |
| `validate_sql.py` | Analyse SQL, autorisations et préparation SQLite |
| `date_guard.py` | Contrôle des périodes temporelles prises en charge |
| `execute_generated.py` | Exécution contrôlée et plafonnement des résultats |
| `chat_exploratory.py` | Conversation exploratoire dans le terminal |
| `export_schema.py` | Export de la structure de Chinook |
| `evaluation/` | Références et tests du constructeur initial |

Les fichiers du parcours initial sont conservés pour réutiliser ses fonctions et comparer les approches.

## Installation sous Windows

### 1. Cloner le dépôt

```powershell
git clone https://github.com/AYOUB10mnsr/Agent_SQL.git
cd Agent_SQL
```

### 2. Créer un environnement Python

Le projet a été utilisé avec Python 3.13.

```powershell
python -m venv .venv
```

### 3. Installer les dépendances

```powershell
.\.venv\Scripts\python.exe -m pip install google-genai python-dotenv pydantic sqlglot streamlit pandas
```

### 4. Vérifier la base

Le fichier doit être présent ici :

```text
data/Chinook_Sqlite.sqlite
```

Si nécessaire, télécharger `Chinook_Sqlite.sqlite` depuis les [versions officielles de Chinook](https://github.com/lerocha/chinook-database/releases).

Utiliser la même version des données pour reproduire les tests de référence.

### 5. Configurer Gemini

Créer un fichier `.env` à la racine :

```dotenv
GEMINI_API_KEY=VOTRE_CLE_API
GEMINI_MODEL=gemini-3.1-flash-lite
```

Ce modèle a été utilisé lors des essais du projet. Son accès, ses quotas et sa disponibilité dépendent du compte et du fournisseur.

Créer une clé depuis [Google AI Studio](https://aistudio.google.com/apikey).

Ne pas publier `.env` ni `.venv/`. Vérifier leur exclusion dans `.gitignore`.

### 6. Exporter le schéma si nécessaire

```powershell
.\.venv\Scripts\python.exe .\export_schema.py
```

Cette commande génère `knowledge/schema.json`.

Le fichier de contexte métier doit également être présent :

```text
knowledge/business_context.json
```

### 7. Tester la connexion au modèle

```powershell
.\.venv\Scripts\python.exe .\test_llm.py
```

## Utilisation avec Streamlit

Lancer l’application :

```powershell
.\.venv\Scripts\python.exe -m streamlit run .\app.py --server.address 127.0.0.1
```

Ouvrir l’adresse indiquée dans le terminal, généralement :

```text
http://localhost:8501
```

Le terminal doit rester ouvert. Pour arrêter le serveur, utiliser `Ctrl + C`.

L’interface permet de :

- Poser une question et répondre aux clarifications.
- Consulter les tableaux de résultats.
- Examiner le SQL et ses paramètres.
- Commencer une nouvelle conversation.
- Réessayer ou abandonner une question en échec.

La mémoire est liée à la session du navigateur. Elle n’est pas sauvegardée durablement et peut être perdue lors d’un rechargement.

## Utilisation dans le terminal

### Conversation exploratoire

```powershell
.\.venv\Scripts\python.exe .\chat_exploratory.py
```

Exemple :

```text
Toi : Quels sont les cinq clients ayant le montant total facturé
le plus élevé en 2010 ?

Assistant : [tableau des cinq clients]

Toi : Et en 2011 ?

Assistant : [classement pour 2011, limité à cinq clients]

Toi : Et les dix premiers ?

Assistant : [classement pour 2011, limité à dix clients]
```

Saisir chaque question sur une seule ligne.

| Commande | Action |
|---|---|
| `/retry` | Relancer la question en attente |
| `/cancel` | Abandonner la question en attente |
| `/reset` | Effacer le contexte |
| `/quit` | Quitter |

### Génération sans exécution

```powershell
.\.venv\Scripts\python.exe .\generate_sql.py
```

### Génération et validation, sans calcul des résultats

```powershell
.\.venv\Scripts\python.exe .\validate_sql.py
```

### Génération, validation et exécution contrôlée

```powershell
.\.venv\Scripts\python.exe .\execute_generated.py
```

## Contrôles techniques

### Validation SQL

Le validateur applique notamment :

- Une seule instruction.
- Une requête `SELECT`, éventuellement avec un `WITH` non récursif.
- Blocage des opérations de modification.
- Refus de `SELECT *`, avec autorisation de `COUNT(*)`.
- Vérification des paramètres fournis.
- Liste autorisée de fonctions.
- Accès limité aux tables et colonnes du schéma de démonstration.
- Blocage des tables système.
- Vérification par préparation SQLite.

Lorsqu’un `LIMIT` global est présent, cette version exige un entier littéral compris entre 1 et 100.

### Exécution

L’exécuteur :

- Revalide la requête avant chaque exécution.
- Utilise une connexion en lecture seule.
- Applique un mécanisme d’autorisation SQLite.
- Vérifie périodiquement un délai configuré à trois secondes.
- Retourne au maximum 100 lignes.
- Signale une troncature lorsqu’elle est détectée.

Le délai concerne le traitement SQLite après les contrôles préalables. Il ne constitue pas une garantie de durée totale exacte.

Un `LIMIT` ne garantit pas un faible coût de calcul.

### Contrôle des dates

La première version reconnaît les bornes directes :

```sql
InvoiceDate >= :date_start
AND InvoiceDate < :date_end
```

Elle peut :

- Bloquer une période entièrement extérieure aux dates présentes.
- Signaler une période partiellement extérieure.
- Refuser des filtres temporels non pris en charge.

Les filtres temporels complexes, certaines sous-requêtes et CTE utilisant `InvoiceDate` ne sont pas encore pris en charge.

Ce contrôle examine le SQL. Il ne prouve pas que la période générée correspond correctement à la question de l’utilisateur.

## Gestion des erreurs

Les appels de génération disposent de deux tentatives au maximum pour certaines erreurs serveur : 500, 502, 503 et 504.

Une attente de trois secondes sépare ces tentatives.

Si le traitement échoue :

- La question reste en attente pendant la session.
- L’utilisateur peut la relancer ou l’abandonner.
- Aucun échange terminé n’est ajouté à l’historique du modèle.

La correction automatique d’une requête SQL invalide n’est pas encore implémentée.

## Évaluation réalisée

### Tests du constructeur initial

```powershell
.\.venv\Scripts\python.exe .\evaluation\test_queries.py
```

Quatre cas ont réussi :

1. Nombre total de factures.
2. Montant total facturé.
3. Quantité totale vendue.
4. Montants facturés par mois.

```text
Bilan : 4/4 tests réussis.
```

Ces tests utilisent des interprétations fixées et n’appellent pas Gemini. Ils ne mesurent pas la qualité de la génération SQL exploratoire.

### Tests du validateur

```powershell
.\.venv\Scripts\python.exe .\validate_sql.py --self-test
```

Les onze cas ont réussi, notamment pour :

- Les requêtes autorisées.
- Les CTE de lecture.
- Le blocage des suppressions et instructions multiples.
- Les colonnes inexistantes.
- Les paramètres manquants.
- Les fonctions interdites.
- Les tables système.
- Les limites excessives.

```text
Bilan : 11/11 tests réussis.
```

### Vérifications manuelles

Des résultats ont été comparés à des requêtes de référence dans DB Browser for SQLite :

- 412 factures sur toute la période.
- 37,62 unités monétaires et 7 factures pour avril 2010.
- 37,62 unités monétaires et 7 factures pour mai 2010.
- Classement des cinq premiers clients par montant facturé en 2010.

Les questions de suivi ont également été essayées : changement d’année et passage de cinq à dix clients.

Ces vérifications couvrent des scénarios précis, pas toutes les questions possibles.

## Limites connues

- Gemini peut produire une requête techniquement valide mais incorrecte sur le plan métier.
- Le respect des consignes de calcul n’est pas garanti.
- La mémoire et la demande en attente ne sont pas persistantes.
- Les réponses dépendent de la disponibilité et des quotas du fournisseur.
- Les restrictions du validateur et du contrôle temporel limitent certaines analyses.
- Les requêtes `UNION` à la racine ne sont pas prises en charge.
- Les comparaisons de périodes peuvent être limitées par le contrôle temporel.
- Une absence de résultat ne signifie pas automatiquement zéro vente.
- Les coûts, stocks et paiements nécessaires à certaines analyses sont absents.
- L’application ne permet pas d’établir une cause commerciale à partir d’une simple corrélation.
- L’authentification et les droits distincts par employé ne sont pas implémentés.
- Tous les utilisateurs du prototype partagent le périmètre de démonstration autorisé.
- Les dépendances ne sont pas encore figées dans un fichier de versions.
- Aucun taux global d’exactitude du parcours exploratoire n’a encore été mesuré.

## Évolutions prévues

- Classification des erreurs techniques et des refus de sécurité.
- Une correction automatique limitée pour les erreurs SQL corrigeables.
- Nouvelle validation obligatoire après toute correction.
- Extension du contrôle temporel.
- Évaluation du parcours exploratoire sur un jeu de questions de référence.
- Graphiques adaptés aux résultats.
- Journalisation des exécutions et des temps de réponse.
- Gestion des utilisateurs et des permissions.
- Sauvegarde durable des conversations si nécessaire.
- Documentation des dépendances pour reproduire l’environnement.
- Orchestration avec LangGraph si la complexité des décisions le justifie.
