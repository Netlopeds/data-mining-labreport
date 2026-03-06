"""
==============================================================================
  MARKET-BASKET ANALYSIS "MACHINE LEARNING" SYSTEM
  Using FP-Growth  |  Self-Learning  |  3-Iteration Evolution
  Local Web Dashboard powered by Flask
==============================================================================
WHY FP-GROWTH OVER APRIORI?
  - Apriori scans the database MULTIPLE times (once per k-itemset size) and
    generates an exponentially large set of candidate itemsets.
  - FP-Growth builds a compact Frequent-Pattern Tree (FP-Tree) by scanning
    the database only TWICE, then mines patterns directly from the tree
    without ever generating candidates.
  - For our Pokémon/collectibles dataset (sparse baskets, 57 items, 1050
    transactions from Dataset_A.csv) FP-Growth is better because:
      • Compressed FP-Tree fits large, sparse transaction sets in memory
      • Candidate-free mining avoids exponential blowup on 57-item domain
      • Faster convergence with adaptive threshold auto-selection
      • Clean integration with mlxtend and Pandas
==============================================================================
"""

# --------------------------------------------------------------------------
# IMPORTS
# --------------------------------------------------------------------------
from flask import Flask, jsonify, render_template, request
import pandas as pd
import numpy as np
from mlxtend.preprocessing import TransactionEncoder
# fpgrowth is the FP-Growth implementation in mlxtend
from mlxtend.frequent_patterns import fpgrowth, association_rules
from werkzeug.utils import secure_filename
from threading import Lock
from datetime import datetime
import csv
import os

# --------------------------------------------------------------------------
# FLASK APP INIT
# --------------------------------------------------------------------------
app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

DATASET_LOCK = Lock()

# --------------------------------------------------------------------------
# TRANSACTION DATA — loaded from Dataset_A.csv
# Each row in the CSV is one basket (items separated by commas).
# The full dataset is split into 3 cumulative batches (approx. thirds) to
# simulate iterative / streaming learning:
#   Iteration 1 → first ~1/3 of transactions  (initial learning)
#   Iteration 2 → first ~2/3 of transactions  (+new arrivals)
#   Iteration 3 → all transactions            (+remaining arrivals)
# --------------------------------------------------------------------------
def _load_transactions_from_csv(path):
    """Read a CSV file — each non-empty row becomes one cleaned transaction list."""
    transactions = []
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            cleaned = []
            for item in row:
                value = str(item).strip()
                if value:
                    cleaned.append(value)
            if cleaned:
                transactions.append(list(dict.fromkeys(cleaned)))
    return transactions


def _default_csv_path():
    return os.path.join(BASE_DIR, "dataset_A.csv")


def _build_batch_sizes(transaction_count):
    return {
        1: max(1, transaction_count // 3),
        2: max(1, (transaction_count * 2) // 3),
        3: transaction_count,
    }

# --------------------------------------------------------------------------
# FP-GROWTH ML ENGINE
# --------------------------------------------------------------------------
class FPGrowthMLEngine:
    """
    Self-learning market-basket engine powered by FP-Growth.

    Intelligent mechanisms implemented:
      1. Auto-Threshold Adaptation  – system finds optimal minsup/minconf
                                       targeting ~10-15 high-quality rules
      2. Drift Detection            – flags items whose support changed >15%
                                       between iterations
      3. Custom Rule Scoring        – weighted score: 0.40*lift_norm
                                                     + 0.35*confidence
                                                     + 0.25*support
      4. Rule Stability Testing     – top-3 rules tested at minsup ±0.05
      5. Model Versioning           – per-iteration snapshots for comparison
    """

    def __init__(self):
        self.iteration_models = {}   # stores model snapshots per iteration
        self.current_iter = 0

    # ── 1. AUTO-THRESHOLD LOGIC ──────────────────────────────────────────
    # ┌─────────────────────────────────────────────────────────────────────┐
    # │  HOW TO CHANGE minsup / minconf                                     │
    # │                                                                     │
    # │  Option A — change the TARGET RULE COUNT (recommended):            │
    # │    Edit target_min and target_max below.                            │
    # │    The system will auto-select the best (minsup, minconf) pair      │
    # │    that produces a rule count in that range.                        │
    # │    Default: target_min=8, target_max=20                             │
    # │                                                                     │
    # │  Option B — hard-code fixed values:                                 │
    # │    After the search loop, add:                                      │
    # │      best_minsup  = 0.30   # your chosen value                     │
    # │      best_minconf = 0.60   # your chosen value                     │
    # │    before the `return` statement.                                   │
    # │                                                                     │
    # │  Option C — disable auto-selection entirely:                        │
    # │    Replace the call to self.auto_threshold() in run_iteration()     │
    # │    with fixed values:                                               │
    # │      auto_minsup, auto_minconf = 0.30, 0.60                        │
    # │      auto_reason = 'Fixed thresholds (manual override)'            │
    # └─────────────────────────────────────────────────────────────────────┘
    def auto_threshold(self, df, target_min=8, target_max=20):
        """
        Walk minsup from 0.10 to 0.50 in steps of 0.05.
        Pick the highest minsup whose rule count falls in [target_min, target_max].
        If no single value satisfies the range, fall back to the value that
        gives the closest count to the midpoint of the range.
        This avoids both 'too few rules' (uninformative) and
        'too many rules' (overwhelming/noisy).
        """
        best_minsup   = 0.01       # sensible default for CSV dataset
        best_minconf  = 0.50
        best_distance = float("inf")
        target_mid    = (target_min + target_max) / 2   # ideal = 14

        candidate_results = []

        # Build a search range that covers both sparse large datasets and
        # small dense ones.  For n >= 100 we scan a fine-grained low range
        # (0.003 – 0.05, step 0.001) plus a coarser high range (0.05 – 0.50);
        # for small datasets the original 0.10–0.50 range is sufficient.
        n_rows = len(df)
        if n_rows >= 100:
            _low  = np.round(np.arange(0.003, 0.051, 0.001), 3)
            _high = np.round(np.arange(0.05,  0.55,  0.05 ), 2)
            _minsup_range = np.unique(np.concatenate([_low, _high]))
        else:
            _minsup_range = np.round(np.arange(0.10, 0.55, 0.05), 2)

        # Include higher confidence thresholds so sparse datasets can still
        # yield rules even when support is very low.
        _minconf_values = [0.50, 0.60, 0.70, 0.80, 0.90]

        for ms in _minsup_range:
            ms = round(float(ms), 3)
            try:
                fi = fpgrowth(df, min_support=ms, use_colnames=True, max_len=None)
                if fi.empty:
                    continue
                for mc in _minconf_values:
                    r = association_rules(fi, metric="confidence", min_threshold=mc)
                    rule_count = len(r)
                    dist = abs(rule_count - target_mid)
                    candidate_results.append({
                        "minsup": ms, "minconf": mc,
                        "rule_count": rule_count, "dist": dist
                    })
                    if target_min <= rule_count <= target_max:
                        if dist < best_distance:
                            best_distance = dist
                            best_minsup   = ms
                            best_minconf  = mc
            except Exception:
                continue

        # If no candidate landed in the range, pick closest
        if best_distance == float("inf") and candidate_results:
            best = min(candidate_results, key=lambda x: x["dist"])
            best_minsup  = best["minsup"]
            best_minconf = best["minconf"]

        lo_str = f"{_minsup_range[0]:.3f}"
        hi_str = f"{_minsup_range[-1]:.2f}"
        mc_str = str(_minconf_values)
        reasoning = (
            f"Tried minsup ∈ [{lo_str}–{hi_str}] × minconf ∈ {mc_str}. "
            f"Targeted {target_min}–{target_max} rules (ideal ≈ {target_mid:.0f}). "
            f"Selected minsup={best_minsup}, minconf={best_minconf}."
        )
        return best_minsup, best_minconf, reasoning

    # ── 2. CUSTOM RULE SCORING ────────────────────────────────────────────
    def score_rules(self, rules_df):
        """
        Composite quality score for each rule:
          score = 0.40 * (lift normalised to 0-1)
                + 0.35 * confidence
                + 0.25 * support
        Normalisation: lift_norm = (lift - 1) / (max_lift - 1 + ε)
        A lift of 1 means independence; higher is better.
        """
        if rules_df.empty:
            return rules_df
        max_lift = rules_df["lift"].max()
        min_lift = 1.0
        eps = 1e-9
        rules_df = rules_df.copy()
        rules_df["lift_norm"] = (rules_df["lift"] - min_lift) / (max_lift - min_lift + eps)
        rules_df["score"] = (
            0.40 * rules_df["lift_norm"]
          + 0.35 * rules_df["confidence"]
          + 0.25 * rules_df["support"]
        )
        return rules_df

    # ── 3. DRIFT DETECTION ────────────────────────────────────────────────
    def detect_drift(self, prev_model, curr_model, threshold=0.15):
        """
        Compare single-item (k=1) support between consecutive iterations.
        An item is 'drifting' if |new_support - old_support| > threshold (15%).
        Drift means buying patterns are shifting — the system should update
        its recommendations accordingly (which it does automatically each iteration).
        """
        if prev_model is None:
            return []

        def support_map(model):
            fi = model["frequent_itemsets"]
            k1 = fi[fi["k"] == 1]
            return {list(row["itemsets"])[0]: row["support"]
                    for _, row in k1.iterrows()}

        prev_map = support_map(prev_model)
        curr_map = support_map(curr_model)
        drift = []
        for item, curr_sup in curr_map.items():
            if item in prev_map:
                delta = curr_sup - prev_map[item]
                if abs(delta) > threshold:
                    direction = "↑ rising" if delta > 0 else "↓ falling"
                    drift.append({
                        "item": item,
                        "prev_support": round(prev_map[item], 3),
                        "curr_support": round(curr_sup, 3),
                        "delta": round(delta, 3),
                        "direction": direction
                    })
        return drift

    # ── 4. RULE STABILITY TEST ────────────────────────────────────────────
    def stability_test(self, df, top_rules, base_minsup, base_minconf):
        """
        Test whether the top-3 rules remain frequent when minsup is nudged
        up (+0.05) and down (-0.05).
        A 'stable' rule appears in all three threshold settings.
        This validates that recommendations are robust, not threshold-artifacts.
        """
        results = []
        test_sup = [
            round(max(0.05, base_minsup - 0.05), 2),
            base_minsup,
            round(min(0.90, base_minsup + 0.05), 2)
        ]
        if top_rules.empty:
            return results

        top3 = top_rules.head(3)
        for _, row in top3.iterrows():
            ant = row["antecedents"]
            con = row["consequents"]
            appearances = {}
            for ms in test_sup:
                try:
                    fi   = fpgrowth(df, min_support=ms, use_colnames=True)
                    ruls = association_rules(fi, metric="confidence",
                                            min_threshold=base_minconf)
                    found = any(
                        (r["antecedents"] == ant and r["consequents"] == con)
                        for _, r in ruls.iterrows()
                    )
                    appearances[ms] = found
                except Exception:
                    appearances[ms] = False

            stable = all(appearances.values())
            results.append({
                "rule":       f"{set(ant)} → {set(con)}",
                "antecedent": "{" + ", ".join(sorted(ant)) + "}",
                "consequent": "{" + ", ".join(sorted(con)) + "}",
                "appearances": {str(k): v for k, v in appearances.items()},
                "stable":     stable,
                "verdict":    "✅ STABLE" if stable else "⚠️ UNSTABLE"
            })
        return results

    # ── CORE: RUN A SINGLE ITERATION ─────────────────────────────────────
    def run_iteration(self, transactions, iteration_number):
        """
        Full pipeline for one iteration:
          1. One-hot encode
          2. Auto-threshold selection
          3. FP-Growth frequent itemset mining
          4. Association rule generation + custom scoring
          5. Drift detection vs previous iteration
          6. Rule stability test
          7. Build all recommendation outputs
          8. Snapshot model for versioning
        """
        N = len(transactions)

        # Step 1: One-hot encode ─────────────────────────────────────────
        te = TransactionEncoder()
        df = pd.DataFrame(
            te.fit(transactions).transform(transactions),
            columns=te.columns_
        )

        # Step 2: Auto-threshold selection ──────────────────────────────
        auto_minsup, auto_minconf, auto_reason = self.auto_threshold(df)

        # Step 3: FP-Growth mining ───────────────────────────────────────
        fi = fpgrowth(df, min_support=auto_minsup, use_colnames=True, max_len=None)
        fi["support_count"] = (fi["support"] * N).round().astype(int)
        fi["k"] = fi["itemsets"].apply(len)
        fi_sorted = fi.sort_values(
            ["k", "support", "itemsets"],
            ascending=[True, False, True]
        ).reset_index(drop=True)

        # Step 4: Rule generation + scoring ─────────────────────────────
        try:
            rules = association_rules(fi_sorted, metric="confidence",
                                      min_threshold=auto_minconf)
        except Exception:
            rules = pd.DataFrame()

        if not rules.empty:
            rules["support_count"] = (rules["support"] * N).round().astype(int)
            rules = self.score_rules(rules)
            rules.sort_values("score", ascending=False, inplace=True)
            rules.reset_index(drop=True, inplace=True)

        # Step 5: Drift detection ────────────────────────────────────────
        prev_model = self.iteration_models.get(iteration_number - 1)
        current_model_stub = {"frequent_itemsets": fi_sorted}
        drift = self.detect_drift(prev_model, current_model_stub)

        # Step 6: Stability test ─────────────────────────────────────────
        stability = []
        if not rules.empty:
            stability = self.stability_test(df, rules, auto_minsup, auto_minconf)

        # Step 7: Build recommendation outputs ──────────────────────────
        bundles         = self._build_bundles(fi_sorted)
        assoc_rules_out = self._build_rules_output(rules)
        homepage        = self._build_homepage_ranking(fi_sorted)
        freq_together   = self._build_freq_together(fi_sorted)
        cross_sell      = self._build_cross_sell(rules)
        promos          = self._build_promos(fi_sorted, rules)
        biz_insights    = self._build_business_insights(fi_sorted, rules, N)

        # Step 8: Snapshot ───────────────────────────────────────────────
        snapshot = {
            "iteration":          iteration_number,
            "n_transactions":     N,
            "auto_minsup":        auto_minsup,
            "auto_minconf":       auto_minconf,
            "auto_reason":        auto_reason,
            "frequent_itemsets":  fi_sorted,          # kept as DataFrame
            "rules":              rules,               # kept as DataFrame
            "drift":              drift,
            "stability":          stability,
            "bundles":            bundles,
            "assoc_rules":        assoc_rules_out,
            "homepage":           homepage,
            "freq_together":      freq_together,
            "cross_sell":         cross_sell,
            "promos":             promos,
            "biz_insights":       biz_insights,
        }
        self.iteration_models[iteration_number] = snapshot
        self.current_iter = iteration_number
        return snapshot

    # ── RECOMMENDATION BUILDERS ──────────────────────────────────────────

    def _build_bundles(self, fi_sorted):
        """Top frequent itemsets grouped by size k."""
        bundles = []
        for _, row in fi_sorted.iterrows():
            items = sorted(row["itemsets"])
            bundles.append({
                "itemset":       "{" + ", ".join(items) + "}",
                "items":         items,
                "k":             int(row["k"]),
                "support":       round(float(row["support"]), 3),
                "support_count": int(row["support_count"]),
                "explanation":   (
                    f"Bought together in {int(row['support_count'])} transactions "
                    f"({row['support']*100:.1f}% of all baskets). "
                    + ("Bundle discount candidate." if row["k"] >= 2 else "High-traffic single item.")
                )
            })
        return bundles

    def _build_rules_output(self, rules):
        """Serialisable list of top association rules."""
        if rules.empty:
            return []
        out = []
        for _, row in rules.iterrows():
            ant = sorted(row["antecedents"])
            con = sorted(row["consequents"])
            out.append({
                "antecedent":    "{" + ", ".join(ant) + "}",
                "antecedent_items": ant,
                "consequent":    "{" + ", ".join(con) + "}",
                "consequent_items": con,
                "support":       round(float(row["support"]), 3),
                "support_count": int(row["support_count"]),
                "confidence":    round(float(row["confidence"]), 3),
                "lift":          round(float(row["lift"]), 3),
                "leverage":      round(float(row["leverage"]), 3),
                "conviction":    round(float(row["conviction"]) if row["conviction"] != np.inf else 999.0, 3),
                "score":         round(float(row["score"]), 3),
            })
        return out

    def _build_homepage_ranking(self, fi_sorted):
        """
        E-commerce homepage ranking:
        Rank single items by support (popularity).
        Items appearing in more baskets get top slots.
        """
        k1 = fi_sorted[fi_sorted["k"] == 1].copy()
        ranking = []
        for rank, (_, row) in enumerate(k1.iterrows(), 1):
            item = list(row["itemsets"])[0]
            ranking.append({
                "rank":          rank,
                "item":          item,
                "support":       round(float(row["support"]), 3),
                "support_count": int(row["support_count"]),
                "reason":        f"Appears in {int(row['support_count'])} baskets — rank #{rank} on homepage."
            })
        return ranking

    def _build_freq_together(self, fi_sorted):
        """
        'Frequently Bought Together' widget (Amazon-style).
        Uses 2-itemsets and 3-itemsets sorted by support.
        """
        k23 = fi_sorted[fi_sorted["k"].isin([2, 3])].copy()
        widgets = []
        for _, row in k23.head(10).iterrows():
            items = sorted(row["itemsets"])
            widgets.append({
                "items":         items,
                "label":         " + ".join(items),
                "support":       round(float(row["support"]), 3),
                "support_count": int(row["support_count"]),
                "k":             int(row["k"]),
            })
        return widgets

    def _build_cross_sell(self, rules):
        """
        Cross-sell map: for each possible 'cart item', list what to recommend.
        Based on rules where the antecedent is a single item.
        Sorted by confidence so the most reliable suggestion appears first.
        """
        if rules.empty:
            return {}
        cross = {}
        single_ant = rules[rules["antecedents"].apply(len) == 1].copy()
        single_ant.sort_values("confidence", ascending=False, inplace=True)
        for _, row in single_ant.iterrows():
            trigger = list(row["antecedents"])[0]
            rec     = sorted(row["consequents"])
            entry = {
                "recommend": "{" + ", ".join(rec) + "}",
                "items":     rec,
                "confidence": round(float(row["confidence"]), 3),
                "lift":       round(float(row["lift"]), 3),
                "score":      round(float(row["score"]), 3),
            }
            cross.setdefault(trigger, []).append(entry)
        return cross

    def _build_promos(self, fi_sorted, rules):
        """
        Promo suggestion generator:
          • Buy-2-Get-Discount  → top 2-itemsets
          • Bundle Deal         → top 3-itemsets
          • Cross-Sell Promo    → high-confidence 2-item rules
        """
        promos = []

        # Buy-2-Get-Discount
        k2 = fi_sorted[fi_sorted["k"] == 2].head(5)
        for _, row in k2.iterrows():
            items = sorted(row["itemsets"])
            promos.append({
                "type":    "Buy-2-Get-Discount",
                "items":   items,
                "label":   f"Buy {items[0]} + {items[1]} → Get 10% off!",
                "support": round(float(row["support"]), 3),
                "basis":   f"Co-purchased in {int(row['support_count'])}/{int(fi_sorted['support_count'].max())} transactions."
            })

        # Bundle Deal
        k3 = fi_sorted[fi_sorted["k"] == 3].head(3)
        for _, row in k3.iterrows():
            items = sorted(row["itemsets"])
            promos.append({
                "type":    "Bundle Deal",
                "items":   items,
                "label":   f"Bundle: {' + '.join(items)} → Save 15%!",
                "support": round(float(row["support"]), 3),
                "basis":   f"Appears together in {int(row['support_count'])} baskets."
            })

        # Cross-Sell Promo
        if not rules.empty:
            top_rules = rules[rules["confidence"] >= 0.70].head(3)
            for _, row in top_rules.iterrows():
                ant = sorted(row["antecedents"])
                con = sorted(row["consequents"])
                promos.append({
                    "type":    "Cross-Sell Promo",
                    "items":   ant + con,
                    "label":   f"Added {', '.join(ant)} to cart? Get {', '.join(con)} at 5% off!",
                    "support": round(float(row["support"]), 3),
                    "basis":   f"Confidence: {row['confidence']*100:.0f}% | Lift: {row['lift']:.2f}"
                })

        return promos

    def _build_business_insights(self, fi_sorted, rules, N):
        """
        Business intelligence layer:
          • Shelf placement: pair high-lift items close together
          • Slow movers: items with low support — promote or discount
          • Power items: items in many itemsets — place at store entrance
          • Margin opportunity: high-lift pairs for upselling
        """
        insights = []

        # Power items (appear in many frequent itemsets)
        item_freq = {}
        for _, row in fi_sorted.iterrows():
            for item in row["itemsets"]:
                item_freq[item] = item_freq.get(item, 0) + 1
        if item_freq:
            power_item = max(item_freq, key=item_freq.get)
            insights.append({
                "type":    "Power Item",
                "insight": f"'{power_item}' appears in {item_freq[power_item]} frequent itemsets. "
                           f"Place at store entrance and homepage slot #1."
            })

        # Slow movers (k=1, support below median)
        k1 = fi_sorted[fi_sorted["k"] == 1]
        if len(k1) > 1:
            median_sup = k1["support"].median()
            slow = k1[k1["support"] < median_sup]
            for _, row in slow.iterrows():
                item = list(row["itemsets"])[0]
                insights.append({
                    "type":    "Slow Mover",
                    "insight": f"'{item}' support={row['support']:.2f} below median "
                               f"({median_sup:.2f}). Bundle with high-traffic items or discount."
                })

        # Shelf placement (high-lift pairs)
        if not rules.empty:
            best_lift = rules.nlargest(3, "lift")
            for _, row in best_lift.iterrows():
                ant = sorted(row["antecedents"])
                con = sorted(row["consequents"])
                insights.append({
                    "type":    "Shelf Placement",
                    "insight": f"Place {', '.join(ant)} next to {', '.join(con)} "
                               f"(lift={row['lift']:.2f} — {row['lift']:.1f}× more likely than chance)."
                })

        # Margin / upsell
        if not rules.empty and len(rules) > 0:
            top_score = rules.iloc[0]
            ant = sorted(top_score["antecedents"])
            con = sorted(top_score["consequents"])
            insights.append({
                "type":    "Upsell Opportunity",
                "insight": f"When customer buys {', '.join(ant)}, "
                           f"upsell {', '.join(con)} with a combo price. "
                           f"Score={top_score['score']:.3f}, Conf={top_score['confidence']:.2f}."
            })

        return insights

    # ── SNAPSHOT → JSON-SAFE DICT ─────────────────────────────────────────
    def model_to_json(self, snapshot):
        """Convert a snapshot (which contains DataFrames) to a JSON-safe dict."""

        def fi_to_list(fi_df):
            out = []
            for _, row in fi_df.iterrows():
                items = sorted(row["itemsets"])
                out.append({
                    "itemset":       "{" + ", ".join(items) + "}",
                    "items":         items,
                    "k":             int(row["k"]),
                    "support":       round(float(row["support"]), 3),
                    "support_count": int(row["support_count"]),
                })
            return out

        return {
            "iteration":      snapshot["iteration"],
            "n_transactions": snapshot["n_transactions"],
            "auto_minsup":    snapshot["auto_minsup"],
            "auto_minconf":   snapshot["auto_minconf"],
            "auto_reason":    snapshot["auto_reason"],
            "freq_itemsets":  fi_to_list(snapshot["frequent_itemsets"]),
            "rules":          snapshot["assoc_rules"],
            "drift":          snapshot["drift"],
            "stability":      snapshot["stability"],
            "bundles":        snapshot["bundles"],
            "homepage":       snapshot["homepage"],
            "freq_together":  snapshot["freq_together"],
            "cross_sell":     snapshot["cross_sell"],
            "promos":         snapshot["promos"],
            "biz_insights":   snapshot["biz_insights"],
        }


# --------------------------------------------------------------------------
# GLOBAL ENGINE INSTANCE
# The dataset can be replaced at runtime through the upload pipeline.
# --------------------------------------------------------------------------
engine = FPGrowthMLEngine()
ALL_TRANSACTIONS = []
BATCH_SIZES = {}
_CSV_PATH = ""
_DATASET_META = {
    "name": "",
    "source": "",
    "stored_path": "",
    "transaction_count": 0,
    "item_count": 0,
    "batch_sizes": {},
    "processed_at": "",
}


def _build_summary_payload(current_engine):
    """Side-by-side comparison of all 3 iterations."""
    summary = []
    for i in [1, 2, 3]:
        snap = current_engine.iteration_models.get(i)
        if snap:
            rules_df = snap["rules"]
            top_rule = {}
            if not rules_df.empty:
                r = rules_df.iloc[0]
                top_rule = {
                    "antecedent": "{" + ", ".join(sorted(r["antecedents"])) + "}",
                    "consequent": "{" + ", ".join(sorted(r["consequents"])) + "}",
                    "lift":       round(float(r["lift"]), 3),
                    "score":      round(float(r["score"]), 3),
                }
            summary.append({
                "iteration":      i,
                "n_transactions": snap["n_transactions"],
                "auto_minsup":    snap["auto_minsup"],
                "auto_minconf":   snap["auto_minconf"],
                "n_itemsets":     len(snap["frequent_itemsets"]),
                "n_rules":        len(rules_df) if not rules_df.empty else 0,
                "top_rule":       top_rule,
            })
    return summary


def _build_pipeline_report(transactions, batch_sizes, current_engine, dataset_meta):
    unique_items = sorted({item for txn in transactions for item in txn})
    latest = current_engine.iteration_models.get(3) or current_engine.iteration_models.get(current_engine.current_iter)
    latest_rules = latest["assoc_rules"] if latest else []
    latest_itemsets = latest["frequent_itemsets"] if latest is not None else pd.DataFrame()
    top_rule = latest_rules[0] if latest_rules else None
    return [
        {
            "id": "data-source",
            "label": "Data Source",
            "detail": f"Loaded {dataset_meta['name']} from the {dataset_meta['source']} pipeline.",
        },
        {
            "id": "cleaning",
            "label": "Cleaning",
            "detail": f"Normalized {len(transactions)} transactions and removed blank values.",
        },
        {
            "id": "encoding",
            "label": "Encoding",
            "detail": f"Encoded {len(unique_items)} unique items with one-hot transaction vectors.",
        },
        {
            "id": "mining-engine",
            "label": "Mining Engine",
            "detail": f"Ran FP-Growth across batches {batch_sizes[1]} / {batch_sizes[2]} / {batch_sizes[3]}.",
        },
        {
            "id": "rules",
            "label": "Rules",
            "detail": f"Generated {len(latest_rules)} ranked association rules in the latest iteration.",
        },
        {
            "id": "scoring",
            "label": "Scoring",
            "detail": (
                f"Best rule score {top_rule['score']:.3f} with lift {top_rule['lift']:.3f}."
                if top_rule else
                "No qualifying rules reached the current thresholds."
            ),
        },
        {
            "id": "storage",
            "label": "Storage",
            "detail": f"Stored 3 iteration snapshots and saved the source file at {dataset_meta['stored_path']}.",
        },
        {
            "id": "recommendations",
            "label": "Recommendations",
            "detail": (
                f"Prepared {len(latest['homepage'])} homepage ranks, {len(latest['promos'])} promos, and {len(latest_itemsets)} frequent itemsets."
                if latest else
                "No recommendation outputs are available yet."
            ),
        },
    ]


def _build_bootstrap_payload(current_engine=None, include_iteration_one=True):
    current_engine = current_engine or engine
    iteration_one = None
    if include_iteration_one and 1 in current_engine.iteration_models:
        iteration_one = current_engine.model_to_json(current_engine.iteration_models[1])

    return {
        "ready": bool(ALL_TRANSACTIONS),
        "dataset": _DATASET_META,
        "summary": _build_summary_payload(current_engine),
        "items": sorted({item for txn in ALL_TRANSACTIONS for item in txn}),
        "iteration_1": iteration_one,
        "pipeline": _build_pipeline_report(ALL_TRANSACTIONS, BATCH_SIZES, current_engine, _DATASET_META) if ALL_TRANSACTIONS else [],
    }


def _process_dataset(path, dataset_name, source_label):
    global engine, ALL_TRANSACTIONS, BATCH_SIZES, _CSV_PATH, _DATASET_META

    transactions = _load_transactions_from_csv(path)
    if not transactions:
        raise ValueError("The uploaded CSV has no valid transactions.")

    batch_sizes = _build_batch_sizes(len(transactions))
    next_engine = FPGrowthMLEngine()
    for iter_num, size in batch_sizes.items():
        next_engine.run_iteration(transactions[:size], iter_num)

    dataset_meta = {
        "name": dataset_name,
        "source": source_label,
        "stored_path": path,
        "transaction_count": len(transactions),
        "item_count": len({item for txn in transactions for item in txn}),
        "batch_sizes": batch_sizes,
        "processed_at": datetime.now().isoformat(timespec="seconds"),
    }

    with DATASET_LOCK:
        engine = next_engine
        ALL_TRANSACTIONS = transactions
        BATCH_SIZES = batch_sizes
        _CSV_PATH = path
        _DATASET_META = dataset_meta

    print(
        f"[Data] Loaded {dataset_meta['transaction_count']} transactions from {dataset_name}. "
        f"Batches: {batch_sizes[1]} / {batch_sizes[2]} / {batch_sizes[3]}"
    )
    print("[ML Engine] All 3 iterations pre-computed.")
    return _build_bootstrap_payload(next_engine)


def initialize_empty_dataset_state():
    """Start the app with no active dataset until the user uploads one."""
    global engine, ALL_TRANSACTIONS, BATCH_SIZES, _CSV_PATH, _DATASET_META

    with DATASET_LOCK:
        engine = FPGrowthMLEngine()
        ALL_TRANSACTIONS = []
        BATCH_SIZES = {}
        _CSV_PATH = ""
        _DATASET_META = {
            "name": "",
            "source": "",
            "stored_path": "",
            "transaction_count": 0,
            "item_count": 0,
            "batch_sizes": {},
            "processed_at": "",
        }


initialize_empty_dataset_state()

# --------------------------------------------------------------------------
# FLASK ROUTES
# --------------------------------------------------------------------------

@app.route("/")
def index():
    """Serve the main dashboard page."""
    return render_template("index.html")


@app.route("/api/bootstrap")
def bootstrap():
    """Return everything needed to render the initial UI state."""
    return jsonify(_build_bootstrap_payload())


@app.route("/api/pipeline/upload", methods=["POST"])
def upload_pipeline_csv():
    """Accept a CSV upload, rebuild the model, and return fresh dashboard data."""
    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return jsonify({"error": "Please choose a CSV file to upload."}), 400

    if not uploaded.filename.lower().endswith(".csv"):
        return jsonify({"error": "Only CSV uploads are supported."}), 400

    safe_name = secure_filename(uploaded.filename) or "dataset.csv"
    stored_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{safe_name}"
    stored_path = os.path.join(UPLOAD_DIR, stored_name)
    uploaded.save(stored_path)

    try:
        payload = _process_dataset(stored_path, uploaded.filename, "upload")
    except ValueError as exc:
        if os.path.exists(stored_path):
            os.remove(stored_path)
        return jsonify({"error": str(exc)}), 400

    return jsonify(payload)


@app.route("/api/iteration/<int:n>")
def get_iteration(n):
    """
    Return JSON data for iteration n (1, 2, or 3).
    The engine already has all snapshots pre-computed.
    """
    if n not in engine.iteration_models:
        return jsonify({"error": f"Iteration {n} not found."}), 404
    data = engine.model_to_json(engine.iteration_models[n])
    return jsonify(data)


@app.route("/api/cross_sell/<item>")
def cross_sell_item(item):
    """
    Return cross-sell recommendations for a given cart item
    from the latest iteration.
    """
    snap = engine.iteration_models.get(engine.current_iter)
    if snap is None:
        return jsonify({"error": "No model computed yet."}), 500
    recs = snap["cross_sell"].get(item, [])
    return jsonify({"item": item, "recommendations": recs})


@app.route("/api/items")
def get_items():
    """Return the list of all unique items for the cross-sell widget."""
    items = sorted({item for t in ALL_TRANSACTIONS for item in t})
    return jsonify(items)


@app.route("/api/summary")
def get_summary():
    """Return iteration summaries for the active dataset."""
    return jsonify(_build_summary_payload(engine))


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------
if __name__ == "__main__":
    print("\n" + "="*60)
    if _CSV_PATH:
        print(f"  Dataset : {os.path.basename(_CSV_PATH)}")
        print(f"  Records : {len(ALL_TRANSACTIONS)} transactions")
    else:
        print("  Dataset : none loaded yet")
        print("  Action  : upload a CSV from the Pipeline page")
    print("  Open your browser at:  http://127.0.0.1:5000")
    print("="*60 + "\n")
    app.run(debug=False, port=5000)
