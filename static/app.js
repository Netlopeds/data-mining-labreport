
const { useState, useEffect, useRef } = React;

const PRIMARY_PAGES = [
  { id: "overview", label: "Dashboard" },
  { id: "itemsets", label: "Frequent Itemsets" },
  { id: "rules", label: "Association Rules" },
];

const INSIGHT_PAGES = [
  { id: "homepage", label: "Homepage Ranking" },
  { id: "freq-together", label: "Bought Together" },
  { id: "crosssell", label: "Cross-Sell" },
  { id: "promos", label: "Promo Suggestions" },
  { id: "biz-insights", label: "Business Insights" },
];

const DASH_COLORS = {
  coral: "rgba(239, 113, 89, 0.65)",
  coralBorder: "#ef7159",
  teal: "rgba(23, 198, 185, 0.36)",
  tealBorder: "#17c6b9",
  axis: "#71839d",
  grid: "#e4ebf4",
};



// ── Header (logo + inline nav) ───────────────────────────────────────────────
function Header({ activePage, onPageChange }) {
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const insightActive = INSIGHT_PAGES.some(p => p.id === activePage);
  const openDropdown = () => setDropdownOpen(true);
  const closeDropdown = () => setDropdownOpen(false);
  const handleDropdownBlur = (event) => {
    if (!event.currentTarget.contains(event.relatedTarget)) {
      closeDropdown();
    }
  };

  return (
    <header className="site-header">
      <div className="logo">
        <img className="logo-image" src="/static/logo.png" alt="PokeHive" />
        <div className="logo-copy">
          <span className="logo-text">PokeHive</span>
          <span className="logo-subtext">Market Basket Analysis</span>
        </div>
      </div>
      <nav className="header-nav">
        {PRIMARY_PAGES.map(p => (
          <button
            type="button"
            key={p.id}
            className={"nav-item" + (activePage === p.id ? " active" : "")}
            onClick={() => onPageChange(p.id)}
          >{p.label}</button>
        ))}

        <div
          className={"nav-dropdown" + (dropdownOpen ? " open" : "")}
          onMouseEnter={openDropdown}
          onMouseLeave={closeDropdown}
          onFocusCapture={openDropdown}
          onBlurCapture={handleDropdownBlur}
        >
          <button
            type="button"
            className={"nav-item nav-dropdown-trigger" + (insightActive ? " active" : "")}
            aria-haspopup="menu"
            aria-expanded={dropdownOpen ? "true" : "false"}
          >
            Insights
            <span className="nav-caret">▾</span>
          </button>

          <div className="nav-dropdown-menu" role="menu" aria-label="Insights pages">
            {INSIGHT_PAGES.map(p => (
              <button
                type="button"
                key={p.id}
                className={"nav-dropdown-item" + (activePage === p.id ? " active" : "")}
                onClick={() => {
                  onPageChange(p.id);
                  closeDropdown();
                }}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
      </nav>
    </header>
  );
}

function HeroRibbon({ items }) {
  return (
    <div className="hero-ribbon">
      {items.map(item => (
        <span key={item} className="hero-ribbon-chip">{item}</span>
      ))}
    </div>
  );
}

function MetricPill({ label, value, tone = "" }) {
  return (
    <div className={"metric-pill" + (tone ? " " + tone : "")}>
      <span className="metric-pill-label">{label}</span>
      <strong className="metric-pill-value">{value}</strong>
    </div>
  );
}

// ── IterBanner ────────────────────────────────────────────────────────────────
function IterBanner({ currentIter, onIterChange, summaryData, iterData }) {
  const d = iterData[currentIter];

  return (
    <div className="iter-banner-wrap">
      <div className="iter-banner">
        {[1, 2, 3].map(n => {
          const s = summaryData.find(r => r.iteration === n);
          const txns = s ? s.n_transactions : "…";
          const isActive = currentIter === n;
          return (
            <button
              key={n}
              className={"iter-card-btn" + (isActive ? " active" : "")}
              onClick={() => onIterChange(n)}
            >
              <span className="iter-card-num">0{n}</span>
              <span className="iter-card-info">
                <span className="iter-card-title">Iteration {n}</span>
                <span className="iter-card-txns">{txns} transactions</span>
              </span>
              {isActive && d && (
                <span className="iter-card-thresh">
                  sup&nbsp;{d.auto_minsup} · conf&nbsp;{d.auto_minconf}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ── ChartBar (k=1 support) ───────────────────────────────────────────────────
function ChartBar({ data }) {
  const canvasRef = useRef(null);
  const chartRef  = useRef(null);
  useEffect(() => {
    if (!data || !canvasRef.current) return;
    if (chartRef.current) chartRef.current.destroy();
    const k1 = data.freq_itemsets.filter(f => f.k === 1);
    chartRef.current = new Chart(canvasRef.current, {
      type: "bar",
      data: {
        labels: k1.map(f => f.items[0]),
        datasets: [{
          label: "Support",
          data:  k1.map(f => f.support),
          backgroundColor: DASH_COLORS.coral,
          borderColor: DASH_COLORS.coralBorder,
          borderWidth: 1,
          borderRadius: 4,
        }],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: {
          y: { min: 0, max: 1, ticks: { color: DASH_COLORS.axis }, grid: { color: DASH_COLORS.grid } },
          x: { ticks: { color: DASH_COLORS.axis }, grid: { display: false } },
        },
      },
    });
    return () => { if (chartRef.current) { chartRef.current.destroy(); chartRef.current = null; } };
  }, [data]);
  return <canvas ref={canvasRef} height={200} />;
}

// ── ChartBubble (confidence vs lift) ─────────────────────────────────────────
function ChartBubble({ data }) {
  const canvasRef = useRef(null);
  const chartRef  = useRef(null);
  useEffect(() => {
    if (!data || !canvasRef.current || !data.rules.length) return;
    if (chartRef.current) chartRef.current.destroy();
    chartRef.current = new Chart(canvasRef.current, {
      type: "bubble",
      data: {
        datasets: [{
          label: "Rules",
          data: data.rules.map(r => ({
            x: r.confidence, y: r.lift, r: Math.max(4, r.support * 28),
          })),
          backgroundColor: DASH_COLORS.teal,
          borderColor: DASH_COLORS.tealBorder,
          borderWidth: 1,
        }],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: {
          y: {
            title: { display: true, text: "Lift", color: DASH_COLORS.axis },
            ticks: { color: DASH_COLORS.axis }, grid: { color: DASH_COLORS.grid },
          },
          x: {
            title: { display: true, text: "Confidence", color: DASH_COLORS.axis },
            min: 0, max: 1, ticks: { color: DASH_COLORS.axis }, grid: { color: DASH_COLORS.grid },
          },
        },
      },
    });
    return () => { if (chartRef.current) { chartRef.current.destroy(); chartRef.current = null; } };
  }, [data]);
  return <canvas ref={canvasRef} height={200} />;
}

// ── PageOverview ──────────────────────────────────────────────────────────────
function PageOverview({ d, summaryData, currentIter }) {
  if (!d) return <div className="loader"><span className="spinner"></span>Loading…</div>;
  return (
    <div>
      <div className="page-heading hero-heading">
        <div className="page-heading-copy">
          <div className="accent-bar"></div>
          <div className="page-kicker">PokeHive Dashboard</div>
          <h1>PokeHive Command Center</h1>
          <p>Learn which products rise together, which bundles deserve promotion, and which items should dominate the storefront.</p>
          <HeroRibbon items={[
            `${d.n_transactions} baskets analysed`,
            `${d.rules.length} strong rules`,
            `Iteration ${currentIter} active`,
          ]} />
        </div>
        <div className="hero-stat-stack">
          <div className="hero-stat-card">
            <span className="hero-stat-label">Top Lift</span>
            <strong>{d.rules.length ? d.rules[0].lift.toFixed(2) : "0.00"}</strong>
          </div>
          <div className="hero-stat-card alt">
            <span className="hero-stat-label">Best Support</span>
            <strong>{d.freq_itemsets.length ? `${(d.freq_itemsets[0].support * 100).toFixed(1)}%` : "0%"}</strong>
          </div>
        </div>
      </div>

      {/* Timeline */}
      <div className="timeline">
        {[1, 2, 3].map(n => (
          (() => {
            const s = summaryData.find(row => row.iteration === n);
            const labels = {
              1: "Initial Learning",
              2: "Expanded Pattern Map",
              3: "Full Dataset View",
            };
            return (
              <div key={n} className={"tl-step" + (currentIter >= n ? " done" : "")}>
                <div className="tl-dot">{n}</div>
                <div className="tl-label">
                  {labels[n]}
                  <br/>{s ? `${s.n_transactions} transactions` : "Loading..."}
                </div>
              </div>
            );
          })()
        ))}
      </div>

      {/* Stat cards */}
      <div className="stats-grid">
        {[
          { lbl: "Transactions",      val: d.n_transactions,                          sub: "baskets analysed",    cls: "" },
          { lbl: "Frequent Itemsets", val: d.freq_itemsets.length,                    sub: "patterns found",      cls: " accent-teal" },
          { lbl: "Rules Generated",   val: d.rules.length,                            sub: "actionable rules",    cls: " accent-gold" },
          { lbl: "Auto minsup",       val: d.auto_minsup,                             sub: "system-selected",     cls: " accent-dark" },
          { lbl: "Auto minconf",      val: d.auto_minconf,                            sub: "system-selected",     cls: " accent-dark" },
          { lbl: "Top Rule Lift",     val: d.rules.length ? d.rules[0].lift.toFixed(3) : "—", sub: "best association", cls: " accent-green" },
        ].map(c => (
          <div key={c.lbl} className={"stat-card" + c.cls}>
            <div className="lbl">{c.lbl}</div>
            <div className="val">{c.val}</div>
            <div className="sub">{c.sub}</div>
          </div>
        ))}
      </div>

      {/* Auto-threshold reason */}
      <div className="card">
        <div className="card-head">
          <h3>Auto-Threshold Decision</h3>
          <span className="chip">Intelligent Mechanism #1</span>
        </div>
        <div className="reason-box">{d.auto_reason}</div>
      </div>

      {/* Charts */}
      <div className="grid2">
        <div className="card">
          <div className="card-head">
            <h3>Item Support Distribution</h3>
            <span className="chip">k=1 itemsets</span>
          </div>
          <ChartBar data={d} />
        </div>
        <div className="card">
          <div className="card-head">
            <h3>Confidence vs Lift</h3>
            <span className="chip">bubble size = support</span>
          </div>
          <ChartBubble data={d} />
        </div>
      </div>

      {/* Summary table */}
      <div className="card">
        <div className="card-head">
          <h3>Iteration-by-Iteration Comparison</h3>
          <span className="chip">Model versioning</span>
        </div>
        <div className="summary-table-shell compact-color-card">
          <div className="tbl-wrap compact-summary-wrap">
            <table className="compact-summary-table">
              <thead>
                <tr>
                  <th>Iter</th>
                  <th>Traffic</th>
                  <th>Thresholds</th>
                  <th>Patterns</th>
                  <th>Best Rule</th>
                  <th>Score</th>
                </tr>
              </thead>
              <tbody>
                {summaryData.map(row => (
                  <tr key={row.iteration} className={currentIter === row.iteration ? "summary-row-active" : ""}>
                    <td>
                      <div className="summary-iter-badge">0{row.iteration}</div>
                    </td>
                    <td>
                      <div className="summary-stack">
                        <strong>{row.n_transactions}</strong>
                        <span>baskets analysed</span>
                      </div>
                    </td>
                    <td>
                      <div className="summary-stack summary-stack-tight">
                        <span>sup {row.auto_minsup}</span>
                        <span>conf {row.auto_minconf}</span>
                      </div>
                    </td>
                    <td>
                      <div className="summary-patterns">
                        <span className="summary-mini-chip tone-blue">{row.n_itemsets} itemsets</span>
                        <span className="summary-mini-chip tone-gold">{row.n_rules} rules</span>
                      </div>
                    </td>
                    <td>
                      {row.top_rule && row.top_rule.antecedent ? (
                        <div className="summary-rule-block">
                          <span className="summary-rule-part antecedent">{row.top_rule.antecedent}</span>
                          <span className="summary-rule-arrow">→</span>
                          <span className="summary-rule-part consequent">{row.top_rule.consequent}</span>
                        </div>
                      ) : (
                        <span className="summary-empty">No standout rule</span>
                      )}
                    </td>
                    <td>
                      {row.top_rule?.score ? (
                        <div className="summary-score-pill">{row.top_rule.score}</div>
                      ) : (
                        <span className="summary-empty">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── PageItemsets ──────────────────────────────────────────────────────────────
function PageItemsets({ d, searchQ }) {
  if (!d) return <div className="loader"><span className="spinner"></span>Loading…</div>;
  const maxSup = Math.max(...d.freq_itemsets.map(f => f.support), 0.001);
  const rows   = d.freq_itemsets.filter(f =>
    !searchQ || f.items.some(i => i.toLowerCase().includes(searchQ.toLowerCase()))
  );
  return (
    <div>
      <div className="page-heading">
        <div className="accent-bar"></div>
        <div className="page-kicker">Pattern Library</div>
        <h1>Frequent Itemsets</h1>
        <p>Every repeated basket combination that passes the current support threshold.</p>
      </div>
      <div className="card">
        <div className="card-head">
          <h3>All Frequent Itemsets</h3>
          <span className="chip">{rows.length} itemsets</span>
        </div>
        <div className="data-tbl-wrap">
          <table className="data-compact-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Items</th>
                <th>Size</th>
                <th>Count</th>
                <th>Support</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((f, i) => (
                <tr key={i} className={i === 0 ? "data-row-featured" : ""}>
                  <td><div className="data-rank-badge">#{i + 1}</div></td>
                  <td>
                    <div className="item-tag-row">
                      {f.items.map(it => <span key={it} className="item-tag">{it}</span>)}
                    </div>
                  </td>
                  <td><span className="data-size-chip">{f.k}-item</span></td>
                  <td><strong className="data-num">{f.support_count}</strong></td>
                  <td><span className="data-pill tone-blue">{f.support.toFixed(3)}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ── PageRules ─────────────────────────────────────────────────────────────────
function PageRules({ d, searchQ }) {
  if (!d) return <div className="loader"><span className="spinner"></span>Loading…</div>;
  const maxScore = d.rules.length ? Math.max(...d.rules.map(r => r.score), 0.001) : 1;
  const rows = d.rules.filter(r =>
    !searchQ ||
    r.antecedent.toLowerCase().includes(searchQ.toLowerCase()) ||
    r.consequent.toLowerCase().includes(searchQ.toLowerCase())
  );
  return (
    <div>
      <div className="page-heading">
        <div className="accent-bar"></div>
        <div className="page-kicker">Rule Engine</div>
        <h1>Association Rules</h1>
        <p>Confidence, lift, and support blended into a ranked action list for recommendations.</p>
      </div>
      <div className="card">
        <div className="card-head">
          <h3>All Rules</h3>
          <span className="chip">{rows.length} rules</span>
        </div>
        <div className="data-tbl-wrap">
          <table className="data-compact-table rules-compact-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Rule</th>
                <th>Support</th>
                <th>Confidence</th>
                <th>Lift</th>
                <th>Leverage</th>
                <th>Conviction</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className={i === 0 ? "data-row-featured" : ""}>
                  <td><div className="data-rank-badge">#{i + 1}</div></td>
                  <td>
                    <div className="rule-inline-flow">
                      <span className="rule-inline-ant">{r.antecedent}</span>
                      <span className="rule-inline-arrow">→</span>
                      <span className="rule-inline-con">{r.consequent}</span>
                    </div>
                  </td>
                  <td><span className="data-pill">{r.support.toFixed(3)}</span></td>
                  <td><span className="data-pill tone-gold">{(r.confidence * 100).toFixed(0)}%</span></td>
                  <td><span className={"data-pill" + (r.lift >= 1.5 ? " tone-teal" : "")}>{r.lift.toFixed(3)}</span></td>
                  <td><span className="data-pill">{r.leverage.toFixed(3)}</span></td>
                  <td><span className="data-pill">{r.conviction >= 999 ? "∞" : r.conviction.toFixed(3)}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ── PageHomepage ──────────────────────────────────────────────────────────────
function PageHomepage({ d }) {
  if (!d) return <div className="loader"><span className="spinner"></span>Loading…</div>;
  const maxSup     = Math.max(...d.homepage.map(h => h.support), 0.001);
  const badgeClass = ["gold-badge", "silver-badge", "bronze-badge"];
  return (
    <div>
      <div className="page-heading">
        <div className="accent-bar"></div>
        <div className="page-kicker">Front Shelf</div>
        <h1>Homepage Ranking</h1>
        <p>Put your highest-traffic products in the first slots customers see.</p>
      </div>
      <div className="rank-grid">
        {d.homepage.map((h, i) => (
          <div key={h.item} className={"rank-card " + (badgeClass[i] || "")}>
            <div className="rank-badge">#{h.rank}</div>
            <div className="rank-name">{h.item}</div>
            <div className="rank-bar-bg">
              <div className="rank-bar-fill"
                   style={{ width: (h.support / maxSup * 100).toFixed(1) + "%" }}>
              </div>
            </div>
            <div className="rank-sup">{(h.support * 100).toFixed(1)}% · {h.support_count} txns</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── PageFreqTogether ──────────────────────────────────────────────────────────
function PageFreqTogether({ d }) {
  if (!d) return <div className="loader"><span className="spinner"></span>Loading…</div>;
  return (
    <div>
      <div className="page-heading">
        <div className="accent-bar"></div>
        <div className="page-kicker">Bundle Builder</div>
        <h1>Frequently Bought Together</h1>
        <p>Pair and trio bundles that deserve featured placement or combo pricing.</p>
      </div>
      {d.freq_together.length === 0
        ? <div className="empty">No bundles at current threshold.</div>
        : <div className="grid2">
            {d.freq_together.map((ft, i) => (
              <div key={i} className="fbt-card">
                <div className="fbt-badge">{ft.k}-item bundle</div>
                <div className="fbt-items">
                  {ft.items.map((it, idx) => (
                    <React.Fragment key={it}>
                      {idx > 0 && <span className="fbt-join">+</span>}
                      <span className="fbt-item-wrap">
                        <span>{it}</span>
                      </span>
                    </React.Fragment>
                  ))}
                </div>
                <div className="fbt-support">
                  Bought together in <strong>{ft.support_count}</strong> baskets ·
                  support <strong>{(ft.support * 100).toFixed(1)}%</strong>
                </div>
              </div>
            ))}
          </div>}
    </div>
  );
}

// ── PageCrossSell ─────────────────────────────────────────────────────────────
function PageCrossSell({ d, allItems }) {
  const [selected, setSelected] = useState("");
  const [cartItems, setCartItems] = useState([]);
  useEffect(() => {
    if (allItems.length && !selected) setSelected(allItems[0]);
  }, [allItems]);

  if (!d) return <div className="loader"><span className="spinner"></span>Loading…</div>;
  const cartSet = new Set(cartItems);
  const recommendationMap = new Map();
  const rules = Array.isArray(d.rules) ? d.rules : [];

  rules.forEach(rule => {
    const antecedentItems = Array.isArray(rule.antecedent_items) ? rule.antecedent_items : [];
    const consequentItems = Array.isArray(rule.consequent_items) ? rule.consequent_items : [];
    if (!antecedentItems.length || !consequentItems.length) return;

    const antecedentMatched = antecedentItems.every(item => cartSet.has(item));
    if (!antecedentMatched) return;

    consequentItems.forEach(item => {
      if (cartSet.has(item)) return;
      const existing = recommendationMap.get(item) || {
        item,
        matchedRules: 0,
        matchedAntecedents: new Set(),
        bestConfidence: 0,
        bestLift: 0,
        bestScore: 0,
        bestSupport: 0,
      };
      existing.matchedRules += 1;
      antecedentItems.forEach(trigger => existing.matchedAntecedents.add(trigger));
      existing.bestConfidence = Math.max(existing.bestConfidence, rule.confidence);
      existing.bestLift = Math.max(existing.bestLift, rule.lift);
      existing.bestScore = Math.max(existing.bestScore, rule.score || 0);
      existing.bestSupport = Math.max(existing.bestSupport, rule.support || 0);
      recommendationMap.set(item, existing);
    });
  });

  const recs = Array.from(recommendationMap.values())
    .map(rec => ({
      ...rec,
      triggerCount: rec.matchedAntecedents.size,
      triggers: Array.from(rec.matchedAntecedents),
    }))
    .sort((a, b) => {
      if (b.matchedRules !== a.matchedRules) return b.matchedRules - a.matchedRules;
      if (b.triggerCount !== a.triggerCount) return b.triggerCount - a.triggerCount;
      if (b.bestConfidence !== a.bestConfidence) return b.bestConfidence - a.bestConfidence;
      if (b.bestLift !== a.bestLift) return b.bestLift - a.bestLift;
      if (b.bestSupport !== a.bestSupport) return b.bestSupport - a.bestSupport;
      return b.bestScore - a.bestScore;
    })
    .slice(0, 8);

  const addItemToCart = (item) => {
    if (!item) return;
    setCartItems(prev => (prev.includes(item) ? prev : [...prev, item]));
  };

  const removeItemFromCart = (item) => {
    setCartItems(prev => prev.filter(entry => entry !== item));
  };

  return (
    <div>
      <div className="page-heading">
        <div className="accent-bar"></div>
        <div className="page-kicker">Cart Booster</div>
        <h1>Cross-Sell Widget</h1>
        <p>Add products into a live cart and let the model surface the strongest next-buy recommendations.</p>
      </div>
      <div className="card">
        <div className="card-head"><h3>Add to Cart Simulator</h3></div>
        <div className="cs-controls">
          <select className="cs-select" value={selected} onChange={e => setSelected(e.target.value)}>
            {allItems.map(i => (
              <option key={i} value={i}>{i}</option>
            ))}
          </select>
          <button
            className="cs-btn cs-btn-primary"
            type="button"
            onClick={() => addItemToCart(selected)}
            disabled={!selected || cartItems.includes(selected)}
          >
            {cartItems.includes(selected) ? "Already in Cart" : "Add to Cart"}
          </button>
          <button
            className="cs-btn cs-btn-muted"
            type="button"
            onClick={() => setCartItems([])}
            disabled={cartItems.length === 0}
          >
            Clear Cart
          </button>
        </div>

        <div className="cs-cart-shell">
          <div className="cs-cart-head">
            <div>
              <div className="cs-cart-label">Current Cart</div>
              <strong>{cartItems.length} item{cartItems.length === 1 ? "" : "s"}</strong>
            </div>
            <span className="chip">Live recommendations</span>
          </div>
          {cartItems.length === 0 ? (
            <div className="empty">Your cart is empty. Add a product to start generating recommendations.</div>
          ) : (
            <div className="cs-cart-list">
              {cartItems.map(item => (
                <div key={item} className="cs-cart-item">
                  <div>
                    <div className="cs-cart-item-title">{item}</div>
                    <div className="cs-cart-item-sub">Qty 1 • Present in basket model</div>
                  </div>
                  <button className="cs-remove-btn" type="button" onClick={() => removeItemFromCart(item)}>
                    Remove
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="cs-result">
          {cartItems.length === 0
            ? <div className="empty">Recommendations will appear here after items are added to the cart.</div>
            : recs.length === 0
            ? <div className="empty">No cross-sell rules matched the current cart at this iteration.</div>
            : recs.map((r, i) => (
              <div key={i} className="cs-row">
                <div className="cs-row-num">{i + 1}</div>
                <div className="cs-row-main">
                  <div className="cs-row-kicker">Recommended next add</div>
                  <div className="cs-row-items">{r.item}</div>
                  <div className="cs-trigger-list">
                    Triggered by {r.triggers.map((trigger, idx) => (
                      <span key={trigger}>
                        {idx > 0 && <span className="cs-trigger-dot">•</span>}
                        {trigger}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="cs-row-meta">
                  Rules: <strong>{r.matchedRules}</strong><br/>
                  Match: <strong>{r.triggerCount}</strong><br/>
                  Conf: <strong>{(r.bestConfidence * 100).toFixed(0)}%</strong><br/>
                  Lift: <strong>{r.bestLift.toFixed(2)}</strong>
                </div>
                <button className="cs-btn cs-btn-primary cs-rec-btn" type="button" onClick={() => addItemToCart(r.item)}>
                  Add
                </button>
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}

// ── PagePromos ────────────────────────────────────────────────────────────────
function PagePromos({ d }) {
  if (!d) return <div className="loader"><span className="spinner"></span>Loading…</div>;
  const typeClass = { "Buy-2-Get-Discount": "", "Bundle Deal": "bundle", "Cross-Sell Promo": "xsell" };
  return (
    <div>
      <div className="page-heading">
        <div className="accent-bar"></div>
        <div className="page-kicker">Promo Lab</div>
        <h1>Promo Suggestions</h1>
        <p>Offer ideas generated directly from bundle strength and cross-sell confidence.</p>
      </div>
      {d.promos.length === 0
        ? <div className="empty">No promos at current thresholds. Try Iteration 2 or 3.</div>
        : <div className="promo-grid">
            {d.promos.map((p, i) => (
              <div key={i} className={"promo-card " + (typeClass[p.type] || "")}>
                <div className="promo-type">{p.type}</div>
                <div className="promo-label">{p.label}</div>
                <div className="promo-basis">{p.basis}</div>
              </div>
            ))}
          </div>}
    </div>
  );
}

// ── PageBizInsights ───────────────────────────────────────────────────────────
function PageBizInsights({ d }) {
  if (!d) return <div className="loader"><span className="spinner"></span>Loading…</div>;
  const typeMap = {
    "Power Item":         { cls: "badge-power" },
    "Shelf Placement":    { cls: "badge-shelf" },
    "Upsell Opportunity": { cls: "badge-upsell" },
    "Slow Mover":         { cls: "badge-slow" },
  };
  return (
    <div>
      <div className="page-heading">
        <div className="accent-bar"></div>
        <div className="page-kicker">Store Strategy</div>
        <h1>Business Insights</h1>
        <p>Shelf placement, power items, and upsell opportunities derived from real customer baskets.</p>
      </div>
      <div className="card">
        <div className="card-head"><h3>Store Recommendations</h3></div>
        {d.biz_insights.length === 0
          ? <div className="empty">No insights for this iteration.</div>
          : <div className="insight-list">
              {d.biz_insights.map((ins, i) => {
                const { cls } = typeMap[ins.type] || { cls: "badge-power" };
                return (
                  <div key={i} className="insight-row">
                    <span className={"insight-type-badge " + cls}>{ins.type}</span>
                    <div className="insight-text">{ins.insight}</div>
                  </div>
                );
              })}
            </div>}
      </div>
    </div>
  );
}

// ── App (root component) ──────────────────────────────────────────────────────
function App() {
  const [activePage,  setActivePage]  = useState("overview");
  const [currentIter, setCurrentIter] = useState(1);
  const [iterData,    setIterData]    = useState({});
  const [summaryData, setSummaryData] = useState([]);
  const [allItems,    setAllItems]    = useState([]);
  const [searchQ]                     = useState("");

  // Load one iteration (cache in state)
  const loadIter = async (n) => {
    setIterData(prev => {
      if (prev[n]) return prev;            // already cached
      fetch(`/api/iteration/${n}`)
        .then(r => r.json())
        .then(data => setIterData(p => ({ ...p, [n]: data })));
      return prev;
    });
  };

  // Bootstrap on mount
  useEffect(() => {
    Promise.all([
      fetch("/api/summary").then(r => r.json()),
      fetch("/api/items").then(r => r.json()),
      fetch("/api/iteration/1").then(r => r.json()),
    ]).then(([summary, items, iter1]) => {
      setSummaryData(summary);
      setAllItems(items);
      setIterData({ 1: iter1 });
    });
  }, []);

  const handleIterChange = (n) => {
    setCurrentIter(n);
    loadIter(n);
  };

  const d = iterData[currentIter];

  return (
    <div className={"app-shell theme-" + activePage}>
      <Header activePage={activePage} onPageChange={setActivePage} />
      <IterBanner currentIter={currentIter} onIterChange={handleIterChange} summaryData={summaryData} iterData={iterData} />

      <div className="main-content">
        {activePage === "overview"      && <PageOverview     d={d} summaryData={summaryData} currentIter={currentIter} />}
        {activePage === "itemsets"      && <PageItemsets     d={d} searchQ={searchQ} />}
        {activePage === "rules"         && <PageRules        d={d} searchQ={searchQ} />}
        {activePage === "homepage"      && <PageHomepage     d={d} />}
        {activePage === "freq-together" && <PageFreqTogether d={d} />}
        {activePage === "crosssell"     && <PageCrossSell    d={d} allItems={allItems} />}
        {activePage === "promos"        && <PagePromos       d={d} />}
        {activePage === "biz-insights"  && <PageBizInsights  d={d} />}
      </div>
    </div>
  );
}

// ── Mount ─────────────────────────────────────────────────────────────────────
const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
