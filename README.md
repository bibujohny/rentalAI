RentalAI v2
===========

A beautiful, reliable property & lodge management app built with Flask + SQLite.

Features
- Authentication with Flask-Login
- Buildings CRUD with pincodes
- Tenants (monthly) with electricity connection fields
- Lodge (daily + monthly guests) with auto total and checkout
- Dashboard with Chart.js and AI insights via OpenAI GPT-4.1
- News integration: removed per current requirements

Quickstart
1. Create a virtual environment and install dependencies

   ```sh
   /bin/zsh -lc "python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
   ```

2. Set environment variables (optional, but recommended)

   ```sh
   export FLASK_ENV=development
   export OPENAI_API_KEY=your_openai_key
   # export NEWS_API_KEY=your_newsapi_key  # removed feature
   export SECRET_KEY=your_secret
   ```

3. Run the app

   ```sh
   /bin/zsh -lc "python3 rentalai/run.py"
   ```

   Default admin user is seeded: username admin / password admin

Project structure
See the repository tree in the prompt. Main entry: rentalai/run.py

Notes
- Tailwind is via CDN; for production consider bundling.
- AI insights require an OpenAI API key and will show a helpful message if missing.
- News uses NewsAPI when NEWS_API_KEY is provided, otherwise a placeholder card is shown.
