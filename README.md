# Ionic Allocate — MAF & BAF Dashboard

Interactive web dashboard comparing MAF and BAF funds against Allocate schemes.

## Monthly Update Workflow

1. Update `Allocate MAF BAF Data.xlsx` with latest NAV data (keep sheet names `BAF` and `MAF`)
2. Run the refresh script:
   ```
   python update_data.py
   ```
3. Push to GitHub:
   ```
   git add data.json
   git commit -m "Data refresh: <month year>"
   git push
   ```

## GitHub Pages Setup (one-time)

1. Push this folder to a GitHub repository
2. Go to **Settings → Pages → Source: Deploy from branch → main → / (root)**
3. Your dashboard will be live at `https://<your-username>.github.io/<repo-name>/`

## Local Preview

```
cd allocate-dashboard
python -m http.server 8000
```
Then open `http://localhost:8000` in your browser.

## Files

| File | Purpose |
|------|---------|
| `index.html` | Dashboard UI — never needs editing |
| `data.json` | Data file — regenerated monthly |
| `update_data.py` | Monthly refresh script |
| `Allocate MAF BAF Data.xlsx` | Source data (keep in same folder) |
