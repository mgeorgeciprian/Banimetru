# FinRo.ro — Finante, Asigurari & Tehnologie

Romanian personal finance, insurance and tech review website optimized for Google AdSense with 3 automated content agents (Python + Node.js).

## Project Structure

```
finro/
├── website/                    # Main website
│   ├── index.html              # Homepage (AdSense-optimized)
│   ├── css/style.css           # Stylesheet
│   ├── js/main.js              # Interactivity + calculators
│   ├── articles/{finante,asigurari,tech}/
│   └── data/                   # JSON metadata indexes
├── agents/
│   ├── python/                 # Python agents
│   ├── nodejs/                 # Node.js agents
│   └── setup_cron.sh           # Cron automation
└── README.md
```

## Quick Start

Open `website/index.html` in browser or deploy to static hosting.

### Agents: `cd agents/python && pip install -r requirements.txt && python3 agent_finance.py --dry-run`
### Cron: `chmod +x agents/setup_cron.sh && ./agents/setup_cron.sh`

## AdSense: 7 ad zones. Replace `ca-pub-XXXX` with your publisher ID.

## Agents run daily: Finance 06:00, Insurance 07:00, Tech 08:00 EET.

License: Proprietary — AMATECH KRONSOFT SRL
