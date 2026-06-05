# Knowledge Graph Memory System

A web application that combines a **Neo4j graph database**, **OpenAI GPT-4o**, and an **interactive graph visualizer** to build a long-term AI memory system. Users can store, query, update, and delete knowledge as semantic triples (subject → predicate → object), and interact with the graph through natural language chat.

## Features

- **Knowledge graph CRUD** — add, update, and delete subject-predicate-object triples via form or natural language
- **AI chat interface** — converse naturally; the LLM extracts intent and updates the graph automatically
- **Graph visualization** — interactive Cytoscape.js canvas showing entities and their relationships
- **Update history** — full timeline of changes for any triple, with version tracking
- **Search** — query by entity, predicate, or object with paginated results
- **Dual storage** — Neo4j for persistence, NetworkX for fast in-memory operations

## Architecture

```
┌──────────────┐     REST API      ┌─────────────────────┐
│  Browser UI  │ ◄───────────────► │   Flask (app.py)    │
│  Cytoscape   │                   │                     │
│  Chat panel  │                   │  KnowledgeGraph.py  │
└──────────────┘                   │  (Neo4j + NetworkX) │
                                   │                     │
                                   │  LocalLLM.py        │
                                   │  (GPT-4o intent)    │
                                   └─────────┬───────────┘
                                             │
                                    ┌────────▼────────┐
                                    │  Neo4j (Docker) │
                                    └─────────────────┘
```

## Prerequisites

- Python 3.10+
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (for Neo4j)
- [Ollama](https://ollama.com/) with `deepseek-r1:7b` pulled (optional, used for local chat)
- An OpenAI API key (GPT-4o)

## Setup

1. **Clone the repository**
   ```bash
   git clone <repo-url>
   cd graphviz
   ```

2. **Create a virtual environment and install dependencies**
   ```bash
   python -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Set environment variables**
   ```bash
   cp .env.example .env
   # Edit .env and add your OPENAI_API_KEY
   ```

4. **Start the app** (Docker must be running — Neo4j starts automatically)
   ```bash
   python app.py
   ```
   Open [http://localhost:5000](http://localhost:5000).

## Usage

| Action | How |
|--------|-----|
| Add a fact | Fill in Subject / Predicate / Object form and click **Create** |
| Chat to add/query | Type natural language in the chat box, e.g. *"Alice is friends with Bob"* |
| Search | Enter a term, select search type (entity / predicate / object), click **Search** |
| Update a fact | Click **Update** on any row or double-click it |
| View history | Click **Details** to see the full update timeline for a triple |
| Delete | Click **Delete** on a row, or **Delete All** to wipe the graph |

## Project Structure

```
app.py               — Flask routes and OpenAI chat endpoint
knowledgegraph.py    — Neo4j + NetworkX knowledge graph logic
languagemodel.py     — Intent analysis and local LLM wrapper
utils/
  docker.py          — Docker / Neo4j container management
  utils.py           — Debug logging helper
static/
  script.js          — Frontend logic (fetch, Cytoscape, chat)
  styles.css         — UI styles
templates/
  index.html         — Single-page application shell
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | Your OpenAI API key (required) |
| `DEBUG` | Set to `true` to enable debug logging (default: `false`) |

## Tech Stack

- **Backend**: Python, Flask, Flask-CORS
- **Graph DB**: Neo4j (Docker), NetworkX
- **AI**: OpenAI GPT-4o, Ollama (deepseek-r1:7b), spaCy
- **Frontend**: Vanilla JS, Cytoscape.js
- **Deploy**: Gunicorn (Procfile included)
