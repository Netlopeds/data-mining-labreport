from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock
from typing import Any, TypeAlias

import numpy as np
import pandas as pd
from mlxtend.frequent_patterns import association_rules, fpgrowth
from mlxtend.preprocessing import TransactionEncoder

# ---------------------------------------------------------------------------
# Shared type aliases used by the engine and Flask-facing service layer.
# These keep signatures readable when the code passes around JSON-like payloads.
# ---------------------------------------------------------------------------
Transaction: TypeAlias = list[str]
JsonDict: TypeAlias = dict[str, Any]
DatasetMeta: TypeAlias = dict[str, Any]

ITERATION_ORDER = (1, 2, 3)


# ---------------------------------------------------------------------------
# Basic CSV and formatting helpers used across the module.
# This section handles small, reusable transformations that support both the
# mining engine and the Flask service layer.
# ---------------------------------------------------------------------------
def load_transactions_from_csv(path: str) -> list[Transaction]:
    """Read a CSV file where each non-empty row becomes one cleaned transaction."""
    transactions: list[Transaction] = []
    with open(path, encoding="utf-8-sig", newline="") as file_handle:
        reader = csv.reader(file_handle)
        for row in reader:
            # Trim whitespace and drop empty cells so the engine only sees real items.
            cleaned_items = [str(item).strip() for item in row if str(item).strip()]
            if cleaned_items:
                # dict.fromkeys preserves order while removing duplicates in one basket.
                transactions.append(list(dict.fromkeys(cleaned_items)))
    return transactions


def build_batch_sizes(transaction_count: int) -> dict[int, int]:
    # The dashboard learns cumulatively: first third, then two thirds, then all rows.
    return {
        1: max(1, transaction_count // 3),
        2: max(1, (transaction_count * 2) // 3),
        3: transaction_count,
    }


def unique_items(transactions: list[Transaction]) -> list[str]:
    # Flatten all baskets into a sorted unique item list for dropdowns and stats.
    return sorted({item for transaction in transactions for item in transaction})


def itemset_items(itemset: Any) -> list[str]:
    # Sort itemsets so the UI and comparisons use a stable order.
    return sorted(itemset)


def itemset_label(items: list[str]) -> str:
    # Human-friendly rendering used throughout the JSON payloads.
    return "{" + ", ".join(items) + "}"


def empty_dataset_meta() -> DatasetMeta:
    # Default metadata before a user uploads a dataset.
    return {
        "name": "",
        "source": "",
        "stored_path": "",
        "transaction_count": 0,
        "item_count": 0,
        "batch_sizes": {},
        "processed_at": "",
    }


def top_rule_summary(rules_df: pd.DataFrame) -> JsonDict:
    # Pull just the highest-ranked rule for compact summary cards.
    if rules_df.empty:
        return {}

    top_rule = rules_df.iloc[0]
    return {
        "antecedent": itemset_label(itemset_items(top_rule["antecedents"])),
        "consequent": itemset_label(itemset_items(top_rule["consequents"])),
        "lift": round(float(top_rule["lift"]), 3),
        "score": round(float(top_rule["score"]), 3),
    }


def serialize_frequent_itemsets(fi_df: pd.DataFrame) -> list[JsonDict]:
    # Convert DataFrame rows into plain dicts so Flask can jsonify them directly.
    out: list[JsonDict] = []
    for _, row in fi_df.iterrows():
        items = itemset_items(row["itemsets"])
        out.append({
            "itemset": itemset_label(items),
            "items": items,
            "k": int(row["k"]),
            "support": round(float(row["support"]), 3),
            "support_count": int(row["support_count"]),
        })
    return out


def latest_snapshot(current_engine: "FPGrowthMLEngine") -> JsonDict | None:
    # Prefer iteration 3 when it exists; otherwise fall back to the newest completed one.
    return current_engine.iteration_models.get(3) or current_engine.iteration_models.get(current_engine.current_iter)


# ---------------------------------------------------------------------------
# Core mining engine: encodes transactions, mines patterns, scores rules, and
# prepares the recommendation structures consumed by the dashboard.
# ---------------------------------------------------------------------------
class FPGrowthMLEngine:
    """Self-learning market-basket engine powered by FP-Growth."""

    def __init__(self) -> None:
        # Each iteration snapshot is stored so the UI can compare learning stages.
        self.iteration_models: dict[int, JsonDict] = {}
        self.current_iter = 0

    def auto_threshold(
        self,
        df: pd.DataFrame,
        target_min: int = 8,
        target_max: int = 20,
    ) -> tuple[float, float, str]:
        # Search support/confidence pairs and keep the combination that lands
        # closest to the target rule count window.
        best_minsup = 0.01
        best_minconf = 0.50
        best_distance = float("inf")
        target_mid = (target_min + target_max) / 2
        candidate_results: list[dict[str, float | int]] = []

        # Large datasets benefit from a finer low-support sweep.
        row_count = len(df)
        if row_count >= 100:
            low_supports = np.round(np.arange(0.003, 0.051, 0.001), 3)
            high_supports = np.round(np.arange(0.05, 0.55, 0.05), 2)
            minsup_range = np.unique(np.concatenate([low_supports, high_supports]))
        else:
            minsup_range = np.round(np.arange(0.10, 0.55, 0.05), 2)

        # Confidence is tested separately so sparse datasets still have a chance
        # to produce useful rules after support is lowered.
        minconf_values = [0.50, 0.60, 0.70, 0.80, 0.90]

        for minsup in minsup_range:
            minsup = round(float(minsup), 3)
            try:
                # First mine itemsets, then see how many rules each confidence level yields.
                frequent_itemsets = fpgrowth(df, min_support=minsup, use_colnames=True, max_len=None)
                if frequent_itemsets.empty:
                    continue

                for minconf in minconf_values:
                    rules = association_rules(
                        frequent_itemsets,
                        metric="confidence",
                        min_threshold=minconf,
                    )
                    rule_count = len(rules)
                    distance = abs(rule_count - target_mid)
                    candidate_results.append({
                        "minsup": minsup,
                        "minconf": minconf,
                        "rule_count": rule_count,
                        "dist": distance,
                    })
                    if target_min <= rule_count <= target_max and distance < best_distance:
                        best_distance = distance
                        best_minsup = minsup
                        best_minconf = minconf
            except Exception:
                # Some threshold combinations legitimately produce no usable rules.
                continue

        # If nothing lands inside the target window, pick the nearest alternative.
        if best_distance == float("inf") and candidate_results:
            best = min(candidate_results, key=lambda result: float(result["dist"]))
            best_minsup = float(best["minsup"])
            best_minconf = float(best["minconf"])

        reasoning = (
            f"Tried minsup ∈ [{minsup_range[0]:.3f}–{minsup_range[-1]:.2f}] × minconf ∈ {minconf_values}. "
            f"Targeted {target_min}–{target_max} rules (ideal ≈ {target_mid:.0f}). "
            f"Selected minsup={best_minsup}, minconf={best_minconf}."
        )
        return best_minsup, best_minconf, reasoning

    def score_rules(self, rules_df: pd.DataFrame) -> pd.DataFrame:
        # Rank rules with a blended score instead of relying on one metric alone.
        if rules_df.empty:
            return rules_df

        # Lift is normalized first so it can be combined with confidence/support.
        max_lift = rules_df["lift"].max()
        min_lift = 1.0
        eps = 1e-9
        scored_rules = rules_df.copy()
        scored_rules["lift_norm"] = (scored_rules["lift"] - min_lift) / (max_lift - min_lift + eps)
        scored_rules["score"] = (
            0.40 * scored_rules["lift_norm"]
            + 0.35 * scored_rules["confidence"]
            + 0.25 * scored_rules["support"]
        )
        return scored_rules

    def detect_drift(
        self,
        prev_model: JsonDict | None,
        curr_model: JsonDict,
        threshold: float = 0.15,
    ) -> list[JsonDict]:
        # Compare single-item support between iterations to flag major behavior shifts.
        if prev_model is None:
            return []

        def support_map(model: JsonDict) -> dict[str, float]:
            # Drift only uses one-item supports because they are easy to compare
            # across iterations and represent raw demand changes.
            frequent_itemsets = model["frequent_itemsets"]
            single_items = frequent_itemsets[frequent_itemsets["k"] == 1]
            return {
                itemset_items(row["itemsets"])[0]: float(row["support"])
                for _, row in single_items.iterrows()
            }

        previous_support = support_map(prev_model)
        current_support = support_map(curr_model)
        drift: list[JsonDict] = []
        for item, current_value in current_support.items():
            if item not in previous_support:
                continue

            # Positive delta means the item is becoming more common over time.
            delta = current_value - previous_support[item]
            if abs(delta) > threshold:
                drift.append({
                    "item": item,
                    "prev_support": round(previous_support[item], 3),
                    "curr_support": round(current_value, 3),
                    "delta": round(delta, 3),
                    "direction": "↑ rising" if delta > 0 else "↓ falling",
                })
        return drift

    def stability_test(
        self,
        df: pd.DataFrame,
        top_rules: pd.DataFrame,
        base_minsup: float,
        base_minconf: float,
    ) -> list[JsonDict]:
        # Re-run the best rules under nearby support thresholds to see whether
        # the recommendations are robust or overly sensitive.
        if top_rules.empty:
            return []

        # Check each rule at support below, at, and above the chosen setting.
        test_supports = [
            round(max(0.05, base_minsup - 0.05), 2),
            base_minsup,
            round(min(0.90, base_minsup + 0.05), 2),
        ]
        results: list[JsonDict] = []

        for _, row in top_rules.head(3).iterrows():
            antecedents = row["antecedents"]
            consequents = row["consequents"]
            appearances: dict[str, bool] = {}
            for minsup in test_supports:
                try:
                    # Recompute rules from scratch so the test reflects the new threshold.
                    frequent_itemsets = fpgrowth(df, min_support=minsup, use_colnames=True)
                    rules = association_rules(
                        frequent_itemsets,
                        metric="confidence",
                        min_threshold=base_minconf,
                    )
                    appearances[str(minsup)] = any(
                        candidate["antecedents"] == antecedents and candidate["consequents"] == consequents
                        for _, candidate in rules.iterrows()
                    )
                except Exception:
                    appearances[str(minsup)] = False

            stable = all(appearances.values())
            ant_items = itemset_items(antecedents)
            con_items = itemset_items(consequents)
            results.append({
                "rule": f"{set(antecedents)} → {set(consequents)}",
                "antecedent": itemset_label(ant_items),
                "consequent": itemset_label(con_items),
                "appearances": appearances,
                "stable": stable,
                "verdict": "✅ STABLE" if stable else "⚠️ UNSTABLE",
            })
        return results

    def _encode_transactions(self, transactions: list[Transaction]) -> pd.DataFrame:
        # Convert basket rows into the one-hot format required by mlxtend.
        encoder = TransactionEncoder()
        return pd.DataFrame(
            encoder.fit(transactions).transform(transactions),
            columns=encoder.columns_,
        )

    def _mine_frequent_itemsets(
        self,
        encoded_transactions: pd.DataFrame,
        transaction_count: int,
        minsup: float,
    ) -> pd.DataFrame:
        # Mine frequent itemsets and add the derived columns used by the UI.
        frequent_itemsets = fpgrowth(
            encoded_transactions,
            min_support=minsup,
            use_colnames=True,
            max_len=None,
        )
        # support_count and k make the results easier to display and sort later.
        frequent_itemsets["support_count"] = (frequent_itemsets["support"] * transaction_count).round().astype(int)
        frequent_itemsets["k"] = frequent_itemsets["itemsets"].apply(len)
        return frequent_itemsets.sort_values(
            ["k", "support", "itemsets"],
            ascending=[True, False, True],
        ).reset_index(drop=True)

    def _generate_rules(
        self,
        frequent_itemsets: pd.DataFrame,
        transaction_count: int,
        minconf: float,
    ) -> pd.DataFrame:
        # Turn frequent itemsets into scored association rules.
        try:
            rules = association_rules(
                frequent_itemsets,
                metric="confidence",
                min_threshold=minconf,
            )
        except Exception:
            return pd.DataFrame()

        if rules.empty:
            return rules

        # Add transaction counts and the custom ranking score before returning.
        rules["support_count"] = (rules["support"] * transaction_count).round().astype(int)
        rules = self.score_rules(rules)
        return rules.sort_values("score", ascending=False).reset_index(drop=True)

    def run_iteration(self, transactions: list[Transaction], iteration_number: int) -> JsonDict:
        # This is the full per-iteration pipeline used by the app.
        # Each step feeds the next so the snapshot contains both raw mining output
        # and frontend-specific recommendation data.
        transaction_count = len(transactions)
        encoded_transactions = self._encode_transactions(transactions)
        minsup, minconf, reason = self.auto_threshold(encoded_transactions)
        frequent_itemsets = self._mine_frequent_itemsets(
            encoded_transactions,
            transaction_count,
            minsup,
        )
        rules = self._generate_rules(frequent_itemsets, transaction_count, minconf)
        previous_model = self.iteration_models.get(iteration_number - 1)
        current_model = {"frequent_itemsets": frequent_itemsets}

        # Store everything the UI needs for this iteration in one reusable snapshot.
        snapshot = {
            "iteration": iteration_number,
            "n_transactions": transaction_count,
            "auto_minsup": minsup,
            "auto_minconf": minconf,
            "auto_reason": reason,
            "frequent_itemsets": frequent_itemsets,
            "rules": rules,
            "drift": self.detect_drift(previous_model, current_model),
            "stability": self.stability_test(encoded_transactions, rules, minsup, minconf),
            "bundles": self._build_bundles(frequent_itemsets),
            "assoc_rules": self._build_rules_output(rules),
            "homepage": self._build_homepage_ranking(frequent_itemsets),
            "freq_together": self._build_freq_together(frequent_itemsets),
            "cross_sell": self._build_cross_sell(rules),
            "promos": self._build_promos(frequent_itemsets, rules),
            "biz_insights": self._build_business_insights(frequent_itemsets, rules),
        }
        self.iteration_models[iteration_number] = snapshot
        self.current_iter = iteration_number
        return snapshot

    # UI builder methods convert raw mining results into frontend-friendly payloads.
    def _build_bundles(self, fi_sorted: pd.DataFrame) -> list[JsonDict]:
        # Build generic bundle recommendations directly from frequent itemsets.
        bundles: list[JsonDict] = []
        for _, row in fi_sorted.iterrows():
            items = itemset_items(row["itemsets"])
            bundles.append({
                "itemset": itemset_label(items),
                "items": items,
                "k": int(row["k"]),
                "support": round(float(row["support"]), 3),
                "support_count": int(row["support_count"]),
                "explanation": (
                    f"Bought together in {int(row['support_count'])} transactions "
                    f"({row['support'] * 100:.1f}% of all baskets). "
                    + ("Bundle discount candidate." if row["k"] >= 2 else "High-traffic single item.")
                ),
            })
        return bundles

    def _build_rules_output(self, rules: pd.DataFrame) -> list[JsonDict]:
        # Flatten the association-rules DataFrame into a simple list for JSON output.
        if rules.empty:
            return []

        output: list[JsonDict] = []
        for _, row in rules.iterrows():
            antecedent_items = itemset_items(row["antecedents"])
            consequent_items = itemset_items(row["consequents"])
            output.append({
                "antecedent": itemset_label(antecedent_items),
                "antecedent_items": antecedent_items,
                "consequent": itemset_label(consequent_items),
                "consequent_items": consequent_items,
                "support": round(float(row["support"]), 3),
                "support_count": int(row["support_count"]),
                "confidence": round(float(row["confidence"]), 3),
                "lift": round(float(row["lift"]), 3),
                "leverage": round(float(row["leverage"]), 3),
                "conviction": round(float(row["conviction"]) if row["conviction"] != np.inf else 999.0, 3),
                "score": round(float(row["score"]), 3),
            })
        return output

    def _build_homepage_ranking(self, fi_sorted: pd.DataFrame) -> list[JsonDict]:
        # Rank single items by support so the frontend can show popular products first.
        ranking: list[JsonDict] = []
        single_items = fi_sorted[fi_sorted["k"] == 1].copy()
        for rank, (_, row) in enumerate(single_items.iterrows(), 1):
            item = itemset_items(row["itemsets"])[0]
            ranking.append({
                "rank": rank,
                "item": item,
                "support": round(float(row["support"]), 3),
                "support_count": int(row["support_count"]),
                "reason": f"Appears in {int(row['support_count'])} baskets — rank #{rank} on homepage.",
            })
        return ranking

    def _build_freq_together(self, fi_sorted: pd.DataFrame) -> list[JsonDict]:
        # Use 2-item and 3-item sets for an Amazon-style "frequently bought together" block.
        widgets: list[JsonDict] = []
        for _, row in fi_sorted[fi_sorted["k"].isin([2, 3])].head(10).iterrows():
            items = itemset_items(row["itemsets"])
            widgets.append({
                "items": items,
                "label": " + ".join(items),
                "support": round(float(row["support"]), 3),
                "support_count": int(row["support_count"]),
                "k": int(row["k"]),
            })
        return widgets

    def _build_cross_sell(self, rules: pd.DataFrame) -> dict[str, list[JsonDict]]:
        # Convert single-item antecedent rules into a lookup keyed by the trigger item.
        if rules.empty:
            return {}

        cross_sell: dict[str, list[JsonDict]] = {}
        single_item_rules = rules[rules["antecedents"].apply(len) == 1].copy()
        single_item_rules.sort_values("confidence", ascending=False, inplace=True)
        for _, row in single_item_rules.iterrows():
            trigger = itemset_items(row["antecedents"])[0]
            recommended_items = itemset_items(row["consequents"])
            cross_sell.setdefault(trigger, []).append({
                "recommend": itemset_label(recommended_items),
                "items": recommended_items,
                "confidence": round(float(row["confidence"]), 3),
                "lift": round(float(row["lift"]), 3),
                "score": round(float(row["score"]), 3),
            })
        return cross_sell

    def _build_promos(self, fi_sorted: pd.DataFrame, rules: pd.DataFrame) -> list[JsonDict]:
        # Generate marketing-style promo ideas from itemsets first, then from rules.
        promos: list[JsonDict] = []

        # Strong pairs become simple discount suggestions.
        for _, row in fi_sorted[fi_sorted["k"] == 2].head(5).iterrows():
            items = itemset_items(row["itemsets"])
            promos.append({
                "type": "Buy-2-Get-Discount",
                "items": items,
                "label": f"Buy {items[0]} + {items[1]} → Get 10% off!",
                "support": round(float(row["support"]), 3),
                "basis": f"Co-purchased in {int(row['support_count'])}/{int(fi_sorted['support_count'].max())} transactions.",
            })

        # Three-item sets become bundle deals.
        for _, row in fi_sorted[fi_sorted["k"] == 3].head(3).iterrows():
            items = itemset_items(row["itemsets"])
            promos.append({
                "type": "Bundle Deal",
                "items": items,
                "label": f"Bundle: {' + '.join(items)} → Save 15%!",
                "support": round(float(row["support"]), 3),
                "basis": f"Appears together in {int(row['support_count'])} baskets.",
            })

        if rules.empty:
            return promos

        # High-confidence rules become cross-sell promo candidates.
        for _, row in rules[rules["confidence"] >= 0.70].head(3).iterrows():
            antecedent_items = itemset_items(row["antecedents"])
            consequent_items = itemset_items(row["consequents"])
            promos.append({
                "type": "Cross-Sell Promo",
                "items": antecedent_items + consequent_items,
                "label": f"Added {', '.join(antecedent_items)} to cart? Get {', '.join(consequent_items)} at 5% off!",
                "support": round(float(row["support"]), 3),
                "basis": f"Confidence: {row['confidence'] * 100:.0f}% | Lift: {row['lift']:.2f}",
            })
        return promos

    def _build_business_insights(self, fi_sorted: pd.DataFrame, rules: pd.DataFrame) -> list[JsonDict]:
        # Translate mining output into plain-language retail insights.
        insights: list[JsonDict] = []

        # Count how often each item appears across all frequent itemsets.
        item_frequency: dict[str, int] = {}
        for _, row in fi_sorted.iterrows():
            for item in row["itemsets"]:
                item_frequency[item] = item_frequency.get(item, 0) + 1

        # The most connected item is treated as a "power item".
        if item_frequency:
            power_item = max(item_frequency, key=item_frequency.get)
            insights.append({
                "type": "Power Item",
                "insight": f"'{power_item}' appears in {item_frequency[power_item]} frequent itemsets. Place at store entrance and homepage slot #1.",
            })

        # Single items below the median support are highlighted as slow movers.
        single_items = fi_sorted[fi_sorted["k"] == 1]
        if len(single_items) > 1:
            median_support = single_items["support"].median()
            slow_movers = single_items[single_items["support"] < median_support]
            for _, row in slow_movers.iterrows():
                item = itemset_items(row["itemsets"])[0]
                insights.append({
                    "type": "Slow Mover",
                    "insight": f"'{item}' support={row['support']:.2f} below median ({median_support:.2f}). Bundle with high-traffic items or discount.",
                })

        # High-lift rules suggest items that should be placed near each other.
        if not rules.empty:
            for _, row in rules.nlargest(3, "lift").iterrows():
                antecedent_items = itemset_items(row["antecedents"])
                consequent_items = itemset_items(row["consequents"])
                insights.append({
                    "type": "Shelf Placement",
                    "insight": f"Place {', '.join(antecedent_items)} next to {', '.join(consequent_items)} (lift={row['lift']:.2f} — {row['lift']:.1f}× more likely than chance).",
                })

            # The top-scoring rule is also reused as a direct upsell suggestion.
            top_score = rules.iloc[0]
            antecedent_items = itemset_items(top_score["antecedents"])
            consequent_items = itemset_items(top_score["consequents"])
            insights.append({
                "type": "Upsell Opportunity",
                "insight": f"When customer buys {', '.join(antecedent_items)}, upsell {', '.join(consequent_items)} with a combo price. Score={top_score['score']:.3f}, Conf={top_score['confidence']:.2f}.",
            })

        return insights

    def model_to_json(self, snapshot: JsonDict) -> JsonDict:
        # Strip the remaining DataFrame objects out of the snapshot before JSON serialization.
        return {
            "iteration": snapshot["iteration"],
            "n_transactions": snapshot["n_transactions"],
            "auto_minsup": snapshot["auto_minsup"],
            "auto_minconf": snapshot["auto_minconf"],
            "auto_reason": snapshot["auto_reason"],
            "freq_itemsets": serialize_frequent_itemsets(snapshot["frequent_itemsets"]),
            "rules": snapshot["assoc_rules"],
            "drift": snapshot["drift"],
            "stability": snapshot["stability"],
            "bundles": snapshot["bundles"],
            "homepage": snapshot["homepage"],
            "freq_together": snapshot["freq_together"],
            "cross_sell": snapshot["cross_sell"],
            "promos": snapshot["promos"],
            "biz_insights": snapshot["biz_insights"],
        }


    # ---------------------------------------------------------------------------
    # Service layer: owns dataset state and exposes simple payload builders for
    # Flask routes so app.py does not need to know anything about mining details.
    # ---------------------------------------------------------------------------
@dataclass
class MarketBasketService:
    engine: FPGrowthMLEngine = field(default_factory=FPGrowthMLEngine)
    transactions: list[Transaction] = field(default_factory=list)
    batch_sizes: dict[int, int] = field(default_factory=dict)
    dataset_meta: DatasetMeta = field(default_factory=empty_dataset_meta)
    lock: Lock = field(default_factory=Lock)

    def reset_dataset(self) -> None:
        # Reset the application to an empty state before any upload is processed.
        with self.lock:
            self.engine = FPGrowthMLEngine()
            self.transactions = []
            self.batch_sizes = {}
            self.dataset_meta = empty_dataset_meta()

    def process_dataset(self, path: str, dataset_name: str, source_label: str) -> JsonDict:
        # Load a dataset, precompute all three learning iterations, and swap the
        # service state in one place so the Flask app only reads ready-made data.
        transactions = load_transactions_from_csv(path)
        if not transactions:
            raise ValueError("The uploaded CSV has no valid transactions.")

        # Build a fresh engine so the new dataset fully replaces the old one.
        batch_sizes = build_batch_sizes(len(transactions))
        next_engine = FPGrowthMLEngine()
        for iteration_number, size in batch_sizes.items():
            next_engine.run_iteration(transactions[:size], iteration_number)

        # Metadata is kept separately because the dashboard shows it directly.
        dataset_meta = {
            "name": dataset_name,
            "source": source_label,
            "stored_path": path,
            "transaction_count": len(transactions),
            "item_count": len(unique_items(transactions)),
            "batch_sizes": batch_sizes,
            "processed_at": datetime.now().isoformat(timespec="seconds"),
        }

        # Swap all shared state under the lock so readers never see half-updated data.
        with self.lock:
            self.engine = next_engine
            self.transactions = transactions
            self.batch_sizes = batch_sizes
            self.dataset_meta = dataset_meta

        print(
            f"[Data] Loaded {dataset_meta['transaction_count']} transactions from {dataset_name}. "
            f"Batches: {batch_sizes[1]} / {batch_sizes[2]} / {batch_sizes[3]}"
        )
        print("[ML Engine] All 3 iterations pre-computed.")
        return self.build_bootstrap_payload(next_engine)

    def build_summary_payload(self, current_engine: FPGrowthMLEngine | None = None) -> list[JsonDict]:
        # Build the small cross-iteration summary cards shown in the dashboard.
        engine = current_engine or self.engine
        summary: list[JsonDict] = []
        for iteration_number in ITERATION_ORDER:
            snapshot = engine.iteration_models.get(iteration_number)
            if not snapshot:
                continue

            rules_df = snapshot["rules"]
            summary.append({
                "iteration": iteration_number,
                "n_transactions": snapshot["n_transactions"],
                "auto_minsup": snapshot["auto_minsup"],
                "auto_minconf": snapshot["auto_minconf"],
                "n_itemsets": len(snapshot["frequent_itemsets"]),
                "n_rules": len(rules_df) if not rules_df.empty else 0,
                "top_rule": top_rule_summary(rules_df),
            })
        return summary

    def build_pipeline_report(self, current_engine: FPGrowthMLEngine | None = None) -> list[JsonDict]:
        # Describe each high-level processing stage so the pipeline view can explain
        # what happened to the current dataset.
        engine = current_engine or self.engine
        latest = latest_snapshot(engine)
        latest_rules = latest["assoc_rules"] if latest else []
        latest_itemsets = latest["frequent_itemsets"] if latest else pd.DataFrame()
        top_rule = latest_rules[0] if latest_rules else None

        return [
            {
                "id": "data-source",
                "label": "Data Source",
                "detail": f"Loaded {self.dataset_meta['name']} from the {self.dataset_meta['source']} pipeline.",
            },
            {
                "id": "cleaning",
                "label": "Cleaning",
                "detail": f"Normalized {len(self.transactions)} transactions and removed blank values.",
            },
            {
                "id": "encoding",
                "label": "Encoding",
                "detail": f"Encoded {len(unique_items(self.transactions))} unique items with one-hot transaction vectors.",
            },
            {
                "id": "mining-engine",
                "label": "Mining Engine",
                "detail": f"Ran FP-Growth across batches {self.batch_sizes[1]} / {self.batch_sizes[2]} / {self.batch_sizes[3]}.",
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
                    if top_rule
                    else "No qualifying rules reached the current thresholds."
                ),
            },
            {
                "id": "storage",
                "label": "Storage",
                "detail": f"Stored 3 iteration snapshots and saved the source file at {self.dataset_meta['stored_path']}",
            },
            {
                "id": "recommendations",
                "label": "Recommendations",
                "detail": (
                    f"Prepared {len(latest['homepage'])} homepage ranks, {len(latest['promos'])} promos, and {len(latest_itemsets)} frequent itemsets."
                    if latest
                    else "No recommendation outputs are available yet."
                ),
            },
        ]

    def build_bootstrap_payload(
        self,
        current_engine: FPGrowthMLEngine | None = None,
        include_iteration_one: bool = True,
    ) -> JsonDict:
        # Aggregate the initial payload needed to render the dashboard after load/upload.
        engine = current_engine or self.engine
        iteration_one = None
        if include_iteration_one and 1 in engine.iteration_models:
            iteration_one = engine.model_to_json(engine.iteration_models[1])

        return {
            "ready": bool(self.transactions),
            "dataset": self.dataset_meta,
            "summary": self.build_summary_payload(engine),
            "items": unique_items(self.transactions),
            "iteration_1": iteration_one,
            "pipeline": self.build_pipeline_report(engine) if self.transactions else [],
        }

    def get_iteration_payload(self, iteration_number: int) -> JsonDict | None:
        # Return one iteration snapshot in API-safe form.
        snapshot = self.engine.iteration_models.get(iteration_number)
        if snapshot is None:
            return None
        return self.engine.model_to_json(snapshot)

    def get_cross_sell_payload(self, item: str) -> JsonDict | None:
        # Return the latest cross-sell recommendations for one selected item.
        snapshot = latest_snapshot(self.engine)
        if snapshot is None:
            return None
        return {"item": item, "recommendations": snapshot["cross_sell"].get(item, [])}

    def get_items_payload(self) -> list[str]:
        # Used by the UI item picker.
        return unique_items(self.transactions)

    def get_summary_payload(self) -> list[JsonDict]:
        # Convenience wrapper for the summary API endpoint.
        return self.build_summary_payload()

    @property
    def active_dataset_path(self) -> str:
        # Small helper for startup logs and any future status views.
        return str(self.dataset_meta.get("stored_path", ""))
