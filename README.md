# Veille Prix VO – Guyane

Dashboard de veille concurrentielle automatique pour les véhicules d'occasion en Guyane.

## Sources scrapées
- **LeBonCoin** (region Guyane, filtré par marque/modèle)
- **Cyphoma.com** (annonces Guyane)
- **GuyaneOccasions.com** (Somasco)

## Architecture

```
scraper.py          → Fetch XML stock + scrape concurrents → génère index.html + data.json
.github/workflows/  → GitHub Actions : cron 6h00 quotidien → commit → GitHub Pages
```

## Mise en place

### 1. Créer le dépôt GitHub
```bash
git init
git add .
git commit -m "Initial commit"
gh repo create mon-dashboard-vo --public --push --source=.
```

### 2. Activer GitHub Pages
- Aller dans **Settings → Pages**
- Source : **Deploy from a branch**
- Branch : `main`, dossier : `/ (root)`
- Sauvegarder → votre dashboard sera sur `https://VOTRE-ORG.github.io/mon-dashboard-vo/`

### 3. Premier lancement manuel
- Aller dans **Actions → Veille Prix VO → Run workflow**

### 4. Lancement local (test)
```bash
pip install -r requirements.txt
playwright install chromium
python scraper.py           # scraping complet
python scraper.py --no-scrape  # génère juste le HTML depuis le XML (sans scraper)
```

## Fréquence de mise à jour
Automatique chaque jour à **6h00 heure de Paris** via GitHub Actions (gratuit).
Lancement manuel possible depuis l'onglet Actions.
