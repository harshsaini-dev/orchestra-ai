# Retrieval and optional AI setup

## Default: no models or paid APIs

Install `requirements.txt`, start the app, create a workspace, and load the demo. Ask a question in **Knowledge → Retrieval inspector** or **Ask your business**. The system computes BM25 and TF-IDF cosine, fuses ranks, applies lexical reranking and returns exact extracts with citations. The source viewer exposes page/section, document version and chunk identity.

This fallback is lexical retrieval; it is not dense semantic search. Low overlap and flagged instruction-like passages produce abstention. The phrase flagger is a heuristic, while execution authorization remains completely independent of document content.

## Optional local dense retrieval

Install `requirements-dense.txt` into a separate test environment if possible. Obtain a compatible sentence-transformer model yourself and review its license and resource requirements. The app only loads a local directory; it does not download a model implicitly.

PowerShell example:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dense.txt
$env:ORCHESTRA_DENSE = "1"
$env:ORCHESTRA_EMBED_MODEL_PATH = "C:\models\your-local-model"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Each company receives its own hash-named Chroma collection. SQLite active chunks are authoritative. Versioned chunk IDs remove stale index entries before query; normalized local embeddings supply an additional rank list for fusion. If initialization or query fails, the response warns and uses lexical retrieval. Actual embedding inference was not tested in the delivery environment; adapter fallback and fusion logic were tested.

Changing the local embedding model requires removing/rebuilding the `data/dense` cache while the server is stopped. Never delete the SQLite database to rebuild an optional vector cache.

## Optional provider summary drafts

`app/workspace/llm.py` exposes `LLMClient.complete(question, evidence)`. Set `ORCHESTRA_LLM_PROVIDER` to `openai`, `gemini` or `ollama`, plus the corresponding settings below. Use a model identifier supported by your own provider account or local installation; none is hardcoded as a current recommendation.

| Provider | Server settings | Endpoint |
|---|---|---|
| OpenAI | `OPENAI_API_KEY`, `OPENAI_MODEL` | Chat Completions REST |
| Gemini | `GEMINI_API_KEY`, `GEMINI_MODEL` | GenerateContent REST |
| Ollama | `OLLAMA_MODEL` | Fixed loopback `http://127.0.0.1:11434/api/generate` |

Put settings in the server environment or the documented `.env` file. Do not put credentials into frontend code. Optional summaries appear separately from exact cited extracts and carry a verification notice. They cannot choose tools, SQL, memberships or approvals. Provider failure preserves the offline answer. Live provider success was not tested and no paid requests were made.

Original legacy Gemini/Chroma RAG code remains in `app/rag.py` for the earlier milestone. `requirements-rag.txt` installs its optional Chroma dependency. The final workspace's offline path does not depend on it.

API references consulted: SQLAlchemy session documentation, APScheduler 3.x user guide, Sentence Transformers model/encode documentation, Chroma Python client documentation, Google GenerateContent reference and Ollama's API reference. Provider interfaces can change; verify your chosen live model independently.
