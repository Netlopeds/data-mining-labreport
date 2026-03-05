
### How FP-Growth Works

1. Scans the database **exactly twice**:
   - First scan: count individual item frequencies.
   - Second scan: build a compact **FP-Tree** (a prefix-tree that compresses shared
     item prefixes across all transactions).
2. **No candidate generation at all** — mines patterns directly from the FP-Tree by
   building conditional pattern bases.
3. Lower memory footprint: the tree merges shared prefixes, so dense datasets
   compress tightly.
4. Faster per iteration — ideal for our 3-pass self-learning loop.
5. Auto-threshold grid search (30+ combinations per iteration) is feasible in < 1 second.

---

## Why FP-Growth Specifically Fits This Dataset

| Factor | Detail |
|---|---|
| **Dense baskets** | Avg 3–6 items per basket across 10 unique items (~60% fill rate). Dense datasets are Apriori's worst case — candidate count explodes. FP-Growth's conditional pattern bases handle density gracefully. |
| **3-iteration streaming** | Each learning iteration is an independent FP-Growth run. At O(n) per pass vs Apriori's multi-pass overhead, FP-Growth finishes each iteration in milliseconds. |
| **Auto-threshold grid search** | Our selector tries 30+ (minsup × minconf) combinations per iteration. FP-Growth's single-pass efficiency makes this feasible in < 1 second total. |
| **Custom rule scoring** | Score = 0.40·lift_norm + 0.35·confidence + 0.25·support — ranks rules by real business value, not just one metric. |
