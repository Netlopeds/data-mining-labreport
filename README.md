## Intelligent mechanisms

| # | Mechanism | What it does |
|---|---|---|
| 1 | **Auto-Threshold** | Tries minsup × minconf combos, picks the settings that produce 8–20 high-quality rules |
| 2 | **Drift Detection** | Compares single-item support between iterations; flags items that shift > 15 % |
| 3 | **Custom Rule Score** | `0.40·lift_norm + 0.35·confidence + 0.25·support` — ranks rules holistically |
| 4 | **Stability Test** | Checks whether top-3 rules survive minsup ±0.05 nudges |
| 5 | **Model Versioning** | Every iteration is snapshotted; the dashboard compares all three side-by-side |

---

## Project structure

```
Data Mining Group/
├── app.py                  # Flask server + FP-Growth ML engine
├── requirements.txt        # Python dependencies
├── README.md               # This file
├── fp-growth-machinelearning.py   # Original Apriori reference script
└── templates/
    └── index.html          # Full-page interactive dashboard
```

---

## Setup

### Option A — pip (recommended)

```bash
pip install -r requirements.txt
```

### Option B — conda / venv

```bash
# create virtual environment
python -m venv .venv

# activate (Windows)
.venv\Scripts\activate

# install
pip install -r requirements.txt
```

---

## How to run

```bash
python app.py
```

Then open your browser at:

```
http://127.0.0.1:5000
```

The server pre-computes all 3 iterations automatically at startup (takes ~2–5 s).

---

## Dashboard pages

| Page | What you see |
|---|---|
| 📊 Overview | Stats cards, support chart, conf-vs-lift bubble chart, iteration comparison table |
| 📦 Frequent Itemsets | All frequent itemsets with support bars |
| ⚡ Association Rules | All rules with support / confidence / lift / leverage / conviction / custom score |
| 🏠 Homepage Ranking | E-commerce item ranking by basket popularity |
| 🔗 Bought Together | Amazon-style "frequently bought together" widget |
| 🛍️ Cross-Sell Widget | Simulate adding an item to cart → see ML recommendations |
| 🎁 Promo Suggestions | Auto-generated bundle deals, buy-2-get-discount, cross-sell promos |
| 🧠 ML Insights | Drift detection table, rule stability test, threshold evolution chart |
| 💡 Business Insights | Shelf placement, power items, slow movers, upsell opportunities |

## Iteration batches

| Iteration | Transactions | New data |
|---|---|---|
| 1 | 1–10 | Initial learning |
| 2 | 1–15 | +5 new baskets |
| 3 | 1–20 | +5 more baskets |

## Requirements

- Python 3.9 or higher
- flask>=3.1.0
- mlxtend>=0.23.0
- pandas>=2.0.0
- numpy>=1.26.0
- scikit-learn>=1.3.0
- scipy>=1.11.0
