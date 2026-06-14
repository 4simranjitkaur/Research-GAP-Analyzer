Local run (backend)

1. Install Python deps (from project root):

```bash
python -m pip install -r backend/requirements.txt
```

2. Create a `.env` file in `backend/` (copy `.env.example`) and add your keys:

```bash
cp backend/.env.example backend/.env
# then edit backend/.env and fill values
```

On Windows (PowerShell):

```powershell
Copy-Item backend\.env.example backend\.env
notepad backend\.env
```

3. Run the server (from `backend/`):

```bash
cd backend
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

Notes:
- The app requires valid `GROQ_API_KEY` and `TAVILY_API_KEY` to call external LLM/search APIs.
- Frontend static files are inside `frontend/` (no Node/npm required unless you add a build step).
