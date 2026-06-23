# Veille Prix VO – Guyane Occasion

## Contexte projet
Dashboard de veille concurrentielle automatique pour les véhicules d'occasion (VO) en Guyane.
Client : **Guyane Occasion** (groupe GBH) – concessionnaire multi-marques basé à Matoury (ZI Terca).

## Stock
- **Source XML Motork/CarkSpark** : `https://carspark.dealerk.fr/myPortalXML/index?myPortalXMLkey=19eda390-14aa-4b91-b2af-69c30f534da7`
- **250 véhicules** statut FREE au 23/06/2026
- Marques principales : Renault (107), Dacia (38), KIA (29), Nissan (25), Mercedes-Benz (20)
- Prix : 8 999€ à 81 999€

## Sites concurrents scrapés
| Site | Méthode | Statut |
|------|---------|--------|
| **Cyphoma.com** | requests + BeautifulSoup | ✅ Fonctionne |
| **LeBonCoin Guyane** | Playwright (JS) | ⚠️ Bloqué si pas de navigateur |
| **GuyaneOccasions.com** | Playwright (JS) | ⚠️ Site JS lourd |

## Fichiers clés
| Fichier | Rôle |
|---------|------|
| `scraper.py` | Fetch XML + scrape concurrents + génère index.html |
| `index.html` | Dashboard généré (ouvrir dans navigateur) |
| `stock.json` | Cache du stock parsé |
| `requirements.txt` | Dépendances Python |
| `.github/workflows/daily.yml` | Cron GitHub Actions 6h quotidien |

## Architecture
```
XML Motork → scraper.py → stock.json + index.html
                ↓
          Cyphoma.com (search par make+model)
          LeBonCoin Guyane (Playwright)
          GuyaneOccasions.com (Playwright)
```

## Commandes utiles
```powershell
# Générer le dashboard sans scraping (juste le XML)
python scraper.py --no-scrape

# Scraping complet
python scraper.py

# Installer les dépendances
pip install -r requirements.txt
playwright install chromium
```

## État actuel
- ✅ Dashboard HTML fonctionnel avec 250 véhicules
- ✅ Pagination, filtres, tri, badges d'écart de prix
- ✅ Matching concurrent par make/model (Cyphoma)
- ⏳ LeBonCoin et GuyaneOccasions nécessitent Python + Playwright installés
- ⏳ Automatisation GitHub Actions à configurer

## Prochaines étapes possibles
- Installer Python + pip install -r requirements.txt
- Pousser sur GitHub + activer GitHub Pages pour l'auto-update quotidien
- Ajouter plus de sources (occasions973.com quand il sera de retour en ligne)
- Améliorer le matching concurrent (fuzzy match sur version/année)
