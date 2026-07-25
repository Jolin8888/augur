# Deploy Augur on Vercel

This repository includes a Vercel ASGI entrypoint at `api/index.py`.
Python 3.12 is selected through `.python-version`.

## Deploy from Vercel

1. Push this repository to GitHub.
2. Import the GitHub repository in Vercel.
3. Use the default Vercel settings. The included `vercel.json` routes all requests to the FastAPI dashboard app.
4. Add environment variables as needed:
   - `FINNHUB_API_KEY`
   - `ALPHAVANTAGE_API_KEY`
   - `OPENAI_API_KEY`
   - `AUGUR_EDGAR_CONTACT_EMAIL`

## Deploy with GitHub Actions

Create these GitHub repository secrets:

- `VERCEL_TOKEN`
- `VERCEL_ORG_ID`
- `VERCEL_PROJECT_ID`

The `Deploy to Vercel` workflow deploys `main` to production.

## Notes

- The app runs remotely on Vercel. No local Python server is required.
- `.vercelignore` excludes local caches, test output, and build artifacts from the Vercel bundle.
- Some realtime or long-running workflows may need adjustment for serverless limits.
