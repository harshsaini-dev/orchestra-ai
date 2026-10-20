# Run OrchestraAI

1. Extract the ZIP. Open the `orchestra-ai` folder.
2. Install Python 3.11 or newer.
3. Double-click `start.bat` on Windows, or use the exact PowerShell commands in `README.md`.
4. Open http://127.0.0.1:8000.
5. Click **New here? Create an account**. Use an email-shaped local account name and a password of at least 10 characters. No email is sent.
6. Create a company workspace, then click **Load demo data**.
7. Click **Scan workspace**. Watch the agents and open **Issues & fixes** to review a proposal.

The final app has no default username/password and needs no paid API. Internet access is required to install Python packages the first time; the seeded demo itself runs offline.

For a five-minute presentation, follow `docs/demo-script.md`. The exact academic project title is in `README.md`.

If the port is busy, use `--port 8001` in the Uvicorn command and open http://127.0.0.1:8001. If dependencies changed after an earlier phase, rerun `python -m pip install -r requirements.txt` using the virtual-environment Python.

Data is retained in `data/workspace.db`; the earlier order sandbox retains its separate `data/agentflow.db`. Closing and reopening the server does not reset either database. Never delete these files to resolve a startup problem without taking a backup first.
