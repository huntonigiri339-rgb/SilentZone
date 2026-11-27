# SilentZone — Quiet by Design

App-less, venue-driven silent-zone platform powered by **Gemini** and **Google Cloud**.

## Local Development
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8080
https://github.com/huntonigiri339-rgb/SilentZone

cd ~/silentzone-web

cat << 'EOF' > README.md
# SilentZone — Quiet by Design

App-less, venue-driven silent-zone platform powered by Gemini and Google Cloud.

## Stack
- Backend: Python 3.12 + FastAPI + Uvicorn
- AI: Gemini 3.8 Flash / 3.5 Flash Lite (vision schedule extraction + multilingual setup guides)
- Feeds & QR: RFC-5545 .ics calendar feeds + QR codes
- Hosting: Docker / Render / Google Cloud Run
