# Harnais d'évaluation — Agent IA Autonome

Ce dossier répond au livrable #4 du CDC : **"Rapport d'évaluation ...
≥ 20 scénarios de test avec métriques (précision, latence, taux de
succès)"**.

## Ce que ça teste, et ce que ça NE teste PAS

- `../tests/` = tests **unitaires**, tout est mocké (aucun appel réseau).
  Ils vérifient la LOGIQUE de chaque outil, indépendamment du LLM.
- `evaluation/` (ce dossier) = tests **de bout en bout**, contre le VRAI
  déploiement AWS (vraie latence Bedrock, vrai OpenSearch, vraie
  authentification Cognito). C'est ce qui produit les métriques
  demandées par le livrable #4.

Important, à noter tel quel dans votre rapport de stage : les critères
de succès sont des **mots-clés attendus dans la réponse**, pas un
jugement sémantique fin de la qualité de la réponse. C'est volontaire
(un vrai jugement de qualité nécessiterait soit une relecture humaine,
soit un second LLM "juge") — mais ça veut dire que le "taux de succès"
mesuré ici est une mesure de **non-régression grossière**, pas une note
de qualité absolue. Pour la soutenance, il est recommandé de relire
vous-même les réponses complètes des scénarios en échec (elles sont
listées en détail dans `rapport_evaluation.md`) avant de citer le taux
de succès brut.

## Impossible d'exécuter ce harnais sans vos identifiants

Je (Claude) ne peux pas lancer ce harnais moi-même : mon environnement
n'a accès ni à votre URL Lambda déployée, ni à un compte utilisateur
Cognito valide. C'est vous qui devez l'exécuter, en local, avec vos
propres identifiants. Les tests unitaires du harnais lui-même
(`tests/test_evaluation_harness.py`, 27 tests) garantissent déjà que sa
logique de notation est correcte — il ne reste plus qu'à le brancher sur
votre déploiement réel.

## 1. Récupérer un token Cognito (`AGENT_ID_TOKEN`)

Le projet utilise le flow `USER_PASSWORD_AUTH` (sans secret client),
identique à celui de `UI.py`. Avec un utilisateur de test déjà créé
(email + mot de passe) :

```powershell
aws cognito-idp initiate-auth `
    --auth-flow USER_PASSWORD_AUTH `
    --client-id <VOTRE_COGNITO_CLIENT_ID> `
    --auth-parameters USERNAME=<email-de-test>,PASSWORD=<mot-de-passe>
```

La réponse JSON contient `AuthenticationResult.IdToken` — c'est la
valeur à utiliser (PAS `AccessToken`, `verify_id_token` dans
`auth_service.py` attend bien l'**ID token**). Ce token expire (1h par
défaut côté Cognito) : à régénérer si le harnais renvoie des 401.

## 2. Lancer le harnais

```powershell


cd lambda
python -m evaluation.run_deep_evaluation
```

Options utiles :

```powershell
# Ne lancer qu'une catégorie (pratique pour itérer vite)
python -m evaluation.run_evaluation --category calculator

# Ne lancer qu'un scénario précis
python -m evaluation.run_evaluation --scenario mem-01a --scenario mem-01b

# Changer le dossier de sortie
python -m evaluation.run_evaluation --output-dir ./rapport_evaluation
```

## 3. Lire le résultat

Deux fichiers sont générés dans `--output-dir` (par défaut
`./evaluation_report/`) :

- **`rapport_evaluation.md`** : résumé global (taux de succès, latence
  moyenne/médiane/P95), détail par catégorie, tableau par scénario, et
  le texte complet des réponses en échec (pour comprendre pourquoi sans
  avoir à tout relancer). C'est ce fichier à joindre tel quel (ou
  reformaté) au livrable #4.
- **`rapport_evaluation.csv`** : les mêmes données en format tabulaire,
  pour analyse dans Excel ou pour tracer des graphiques d'évolution
  d'une exécution à l'autre.

## 4. Les 22 scénarios

Définis dans `scenarios.py`, répartis en 8 catégories : culture
générale (aucun outil ne doit être déclenché), `calculator`, `weather`,
`web_search`, `rag_interne`, chaînage multi-outils (pattern ReAct),
mémoire conversationnelle sur 2 tours liés, respect du system prompt
(hors-sujet / clarification), et robustesse (message vide, tentative
d'injection dans la calculatrice).

Pour ajouter un scénario : ajoutez une entrée à `SCENARIOS` dans
`scenarios.py`, avec au minimum `id`, `category`, `prompt`, et un
critère de succès (`expects_tool`, `expected_keyword_groups`,
`must_not_contain`, ou `expect_clean_rejection`). Le harnais le
prendra en compte automatiquement, sans aucune autre modification.
