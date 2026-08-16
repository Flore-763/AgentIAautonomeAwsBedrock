# Agent IA Autonome — AWS Bedrock + LangGraph

Ce projet corrige et restructure l'agent ReAct de Smartovate Ltd. Résumé
des changements par rapport à la version précédente (`langgraph_agent.py`
monolithique).

## 1. Ce qui a changé dans la boucle ReAct

### Avant
- Le LLM devait écrire du texte au format libre `Thought / Action / Action
  Input / Observation / Final Answer`.
- Le code reparsait ce texte avec des **regex** (`re.search(r"Action:\s*(\w+)")`, etc.).
- Utilisait `langgraph.prebuilt.ToolExecutor`, **retiré des versions
  récentes de LangGraph**.
- Les messages étaient mutés directement (`state["messages"].append(...)`),
  ce qui fonctionne par accident (listes passées par référence) mais casse
  dès qu'un vrai checkpointer sérialise l'état.
- La météo était simulée (`random.choice`), ce qui ne respecte pas l'US 3.1
  ("récupérer des données en temps réel via une API externe").

### Après
- **Tool calling natif** de Claude via `ChatBedrockConverse.bind_tools(...)` :
  Claude renvoie directement `AIMessage.tool_calls` (nom d'outil + arguments
  déjà typés), sans passer par du texte libre à reparser. Cela règle
  directement le **Bug 2** du cahier des charges (hallucination / mauvais
  format des paramètres d'outils) et réduit fortement le risque d'erreur
  `ValidationException` ("Requete invalide envoyee a Bedrock") côté Bedrock,
  qui exige une correspondance stricte entre chaque `tool_use` et son
  `tool_result`.
- **`Annotated[List[BaseMessage], add_messages]`** dans `graph/state.py` :
  le "reducer" officiel de LangGraph qui ajoute proprement les nouveaux
  messages à la liste au lieu de la remplacer — plus de mutation manuelle.
- **`langgraph.prebuilt.ToolNode`** n'est même pas utilisé tel quel : un
  nœud `call_tools` "maison" (dans `graph/nodes.py`) est écrit pour pouvoir
  y ajouter la journalisation DynamoDB et la détection de boucle, tout en
  restant sur les primitives stables de LangGraph (`StateGraph`, `END`,
  `add_conditional_edges`, `MemorySaver`).
- **Deux garde-fous explicites** (arêtes conditionnelles) :
  - `max_iterations` : nombre max d'itérations atteint,
  - `loop_detected` : le même outil + mêmes arguments répétés 3 fois de suite.
- **Outil météo réel** (`tools/weather.py`) via l'API publique
  [Open-Meteo](https://open-meteo.com) (géocodage + prévisions), sans clé
  d'API.
- **Nouvel outil calculatrice** (`tools/calculator.py`), avec parsing sûr
  via `ast` (jamais de `eval()`).

## 2. Mémoire conversationnelle — remplacement de `ConversationBufferWindowMemory`

`ConversationBufferWindowMemory` est dépréciée dans les versions récentes
de LangChain. Elle est remplacée par **`DynamoDBChatMessageHistory`**
(`services/memory_service.py`), une classe qui implémente l'interface
standard `BaseChatMessageHistory` de LangChain :

- même comportement de fenêtre glissante (les N derniers échanges),
- persistance DynamoDB conservée à l'identique,
- compatible nativement avec `RunnableWithMessageHistory` si vous voulez
  brancher, ailleurs dans le projet, une simple chaîne LangChain sans
  passer par LangGraph (voir `create_runnable_with_history(...)` en bas de
  `services/memory_service.py`, fourni à titre d'exemple).

Le graphe LangGraph, lui, reçoit directement la liste de messages déjà
chargée (`AgentState.messages`) — un `MemorySaver` (checkpointer LangGraph,
en RAM) est aussi branché sur le graphe pour l'inspection/debug d'une seule
exécution, mais ce n'est **pas** ce qui assure la persistance entre deux
requêtes HTTP différentes (Lambda peut redémarrer un nouveau
micro-environnement à tout moment) : cette persistance inter-requêtes
reste assurée par DynamoDB, comme avant.

## 3. Structure du projet

```
lambda/
│
├── agent_handler.py        # Point d'entrée Lambda : HTTP uniquement
│
├── services/
│   ├── agent_service.py     # Orchestration : mémoire + appel du graphe + sauvegarde
│   ├── memory_service.py    # Persistance DynamoDB + DynamoDBChatMessageHistory
│   ├── bedrock_service.py   # Client Bedrock (ChatBedrockConverse, embeddings Titan)
│   └── prompt_service.py    # System prompt + formatage des souvenirs long terme
│
├── graph/
│   ├── state.py             # AgentState (TypedDict + reducer add_messages)
│   ├── nodes.py             # call_model, call_tools, finalize, garde-fous, routing
│   └── workflow.py          # Construction/compilation du StateGraph
│
├── tools/
│   ├── weather.py           # Météo réelle (Open-Meteo)
│   ├── search.py            # Recherche documentaire (RAG, OpenSearch)
│   └── calculator.py        # Calculatrice sûre (ast, pas d'eval)
│
├── vector_store.py           # Wrapper OpenSearch (recherche vectorielle k-NN)
├── opensearch_config.py      # Client OpenSearch Serverless (AOSS) + auth SigV4
├── config.py                 # Clients boto3 (DynamoDB, Bedrock Runtime)
├── models.py                 # Dataclasses de documentation du contrat d'API
├── utils.py                  # Helpers (timestamps, TTL, sérialisation Decimal)
├── index_pdf.py               # Script d'indexation des PDF (documents/)
├── create_vector_index.py    # Création de l'index OpenSearch (mapping k-NN)
├── documents/                 # PDF à indexer dans la base de connaissances
├── requirements.txt
└── Dockerfile
```

## 4. Comment lire le flux d'une requête

1. `agent_handler.lambda_handler` reçoit l'event API Gateway, extrait
   `session_id` / `message`.
2. `services/agent_service.process_chat_message(...)` :
   - charge la mémoire court terme (`get_chat_history`),
   - calcule l'embedding du message et cherche les souvenirs long terme
     pertinents (`vector_store.semantic_search`),
   - construit l'état initial du graphe et l'exécute (`graph.invoke(...)`),
   - sauvegarde le nouvel échange (DynamoDB + OpenSearch).
3. À l'intérieur du graphe (`graph/workflow.py`) :
   - `call_model` : Claude réfléchit, avec les outils bindés.
   - Si Claude demande un outil → `call_tools` l'exécute puis on repasse
     par `call_model` (nouvelle itération).
   - Si Claude répond directement, ou si un garde-fou se déclenche → un
     des 3 nœuds terminaux (`finalize`, `max_iterations`, `loop_detected`)
     produit la réponse finale.

## 5. Points restants du cahier des charges (Partie 3 — Bugs)

- **Bug 1 (dépassement de la limite de tokens)** : couvert par la fenêtre
  glissante de `DynamoDBChatMessageHistory` (défaut : 5 échanges =
  10 messages). Ajustable via le paramètre `window_size` de
  `process_chat_message`.
- **Bug 2 (hallucination sur les outils)** : réglé par le tool calling
  natif (voir section 1).
- **Bug 3 (timeout API Gateway à 29s)** : **non traité par ce rework**
  (hors périmètre de la demande). La boucle ReAct peut toujours dépasser
  29s si plusieurs itérations d'outils s'enchaînent. Pistes pour plus
  tard : réponses en streaming (Server-Sent Events) depuis Bedrock, ou
  détachement de l'exécution vers SQS + WebSockets pour les requêtes
  longues, comme indiqué dans le cahier des charges initial.

## 6. Variables d'environnement attendues

| Variable | Rôle | Défaut |
|---|---|---|
| `TABLE_NAME` | Table DynamoDB de la mémoire conversationnelle | — (obligatoire) |
| `BEDROCK_REGION` | Région AWS pour Bedrock | `us-west-2` |
| `CHAT_MODEL_ID` | Modèle de chat Bedrock (Converse) | `global.anthropic.claude-sonnet-4-6` |
| `EMBEDDING_MODEL_ID` | Modèle d'embedding Bedrock | `amazon.titan-embed-text-v2:0` |
| `OPENSEARCH_ENDPOINT` | Endpoint de la collection OpenSearch Serverless | voir `opensearch_config.py` |
