# Deploy V7 with GitHub + Streamlit Community Cloud

1. Create a **private GitHub repository**.
2. Push this folder to branch `main`.
3. Create a Supabase project and copy its PostgreSQL connection string.
4. On Streamlit Community Cloud create an app with:
   - Repository: your GitHub repo
   - Branch: `main`
   - Main file: `streamlit_app.py`
5. In Advanced settings → Secrets add `DATABASE_URL`, `ADMIN_PASSWORD`, `APP_ENV`.
6. Optional: add Supabase Storage secrets for real private OCT/fundus images.
7. Smoke test Research, Live, Learning and Admin from different browsers.
