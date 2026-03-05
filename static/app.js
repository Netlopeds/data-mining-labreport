
const { useState, useEffect, useRef, useCallback } = React;

const PAGES = [
  { id: "overview",      label: "Dashboard" },
  { id: "itemsets",      label: "Frequent Itemsets" },
  { id: "rules",         label: "Association Rules" },
  { id: "homepage",      label: "Homepage Ranking" },
  { id: "freq-together", label: "Bought Together" },
  { id: "crosssell",     label: "Cross-Sell" },
  { id: "promos",        label: "Promo Suggestions" },
  { id: "biz-insights",  label: "Business Insights" },
];



// ── Header (logo + inline nav) ───────────────────────────────────────────────
function Header({ activePage, onPageChange }) {
  return (
    <header className="site-header">
      <div className="logo">
        <svg className="logo-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M3 3h7v7H3zM14 3h7v7h-7zM14 14h7v7h-7zM3 14h7v7H3z"/>
        </svg>
        <span className="logo-text">Market Basket</span>
      </div>
      <nav className="header-nav">
        {PAGES.map(p => (
          <div
            key={p.id}
            className={"nav-item" + (activePage === p.id ? " active" : "")}
            onClick={() => onPageChange(p.id)}
          >{p.label}</div>
        ))}
      </nav>
    </header>
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
          backgroundColor: "#CC000077",
          borderColor: "#CC0000",
          borderWidth: 1,
          borderRadius: 4,
        }],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: {
          y: { min: 0, max: 1, ticks: { color: "#999" }, grid: { color: "#f0f0f0" } },
          x: { ticks: { color: "#666" }, grid: { display: false } },
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
          backgroundColor: "#2196a677",
          borderColor: "#2196a6",
          borderWidth: 1,
        }],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: {
          y: {
            title: { display: true, text: "Lift", color: "#999" },
            ticks: { color: "#999" }, grid: { color: "#f0f0f0" },
          },
          x: {
            title: { display: true, text: "Confidence", color: "#999" },
            min: 0, max: 1, ticks: { color: "#999" }, grid: { color: "#f0f0f0" },
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
      <div className="page-heading">
        <div className="accent-bar"></div>
        <h1>Dashboard Overview</h1>
        <p>FP-Growth self-learning market-basket engine · school supply store · 3 learning iterations</p>
      </div>

      {/* Timeline */}
      <div className="timeline">
        {[1, 2, 3].map(n => (
          <div key={n} className={"tl-step" + (currentIter >= n ? " done" : "")}>
            <div className="tl-dot">{n}</div>
            <div className="tl-label">
              {n === 1 ? "Initial Learning" : n === 2 ? "+5 Baskets" : "+5 Baskets"}
              <br/>{n === 1 ? "10 transactions" : n === 2 ? "15 total" : "20 total"}
            </div>
          </div>
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
        <div className="tbl-wrap">
          <table>
            <thead>
              <tr>
                <th>Iter</th><th>Transactions</th><th>minsup</th><th>minconf</th>
                <th>Itemsets</th><th>Rules</th><th>Best Rule</th><th>Score</th>
              </tr>
            </thead>
            <tbody>
              {summaryData.map(row => (
                <tr key={row.iteration}>
                  <td><strong>Iter {row.iteration}</strong></td>
                  <td>{row.n_transactions}</td>
                  <td>{row.auto_minsup}</td>
                  <td>{row.auto_minconf}</td>
                  <td>{row.n_itemsets}</td>
                  <td>{row.n_rules}</td>
                  <td style={{ whiteSpace: "normal", maxWidth: 220 }}>
                    {row.top_rule && row.top_rule.antecedent
                      ? <><span style={{ color: "#CC0000", fontWeight: 600 }}>{row.top_rule.antecedent}</span>
                          {" "}<span className="rule-arrow">→</span>{" "}
                          {row.top_rule.consequent}</>
                      : <span style={{ color: "#aaa" }}>—</span>}
                  </td>
                  <td><strong>{row.top_rule?.score ?? "—"}</strong></td>
                </tr>
              ))}
            </tbody>
          </table>
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
        <h1>Frequent Itemsets</h1>
        <p>All item combinations meeting the auto-selected support threshold</p>
      </div>
      <div className="card">
        <div className="card-head">
          <h3>All Frequent Itemsets</h3>
          <span className="chip">{rows.length} itemsets</span>
        </div>
        <div className="tbl-wrap">
          <table>
            <thead>
              <tr><th>#</th><th>Itemset</th><th>k</th><th>Count</th><th>Support</th><th>Bar</th></tr>
            </thead>
            <tbody>
              {rows.map((f, i) => (
                <tr key={i} className={i === 0 ? "top-row" : ""}>
                  <td style={{ color: "#aaa" }}>{i + 1}</td>
                  <td>{f.items.map(it => <span key={it} className="item-tag">{it}</span>)}</td>
                  <td><strong>{f.k}</strong></td>
                  <td>{f.support_count}</td>
                  <td>{f.support.toFixed(3)}</td>
                  <td>
                    <div className="bar-wrap">
                      <div className="bar-bg">
                        <div className="bar-fill teal"
                             style={{ width: (f.support / maxSup * 100).toFixed(1) + "%" }}>
                        </div>
                      </div>
                      <span style={{ fontSize: ".72rem", color: "#999" }}>
                        {(f.support * 100).toFixed(1)}%
                      </span>
                    </div>
                  </td>
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
        <h1>Association Rules</h1>
        <p>Ranked by composite score · 0.40×lift_norm + 0.35×confidence + 0.25×support</p>
      </div>
      <div className="card">
        <div className="card-head">
          <h3>All Rules</h3>
          <span className="chip">{rows.length} rules</span>
        </div>
        <div className="tbl-wrap">
          <table>
            <thead>
              <tr>
                <th>#</th><th>Antecedent</th><th></th><th>Consequent</th>
                <th>Count</th><th>Support</th><th>Confidence</th>
                <th>Lift</th><th>Leverage</th><th>Conviction</th><th>Score</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className={i === 0 ? "top-row" : ""}>
                  <td style={{ color: "#aaa" }}>{i + 1}</td>
                  <td style={{ color: "#CC0000", fontWeight: 600 }}>{r.antecedent}</td>
                  <td><span className="rule-arrow">→</span></td>
                  <td style={{ fontWeight: 600 }}>{r.consequent}</td>
                  <td>{r.support_count}</td>
                  <td>{r.support.toFixed(3)}</td>
                  <td>
                    <div className="bar-wrap">
                      <div className="bar-bg">
                        <div className="bar-fill gold"
                             style={{ width: (r.confidence * 100).toFixed(1) + "%" }}>
                        </div>
                      </div>
                      <span style={{ fontSize: ".72rem" }}>
                        {(r.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                  </td>
                  <td style={{
                    color: r.lift >= 1.5 ? "#2196a6" : "#333",
                    fontWeight: r.lift >= 1.5 ? 700 : 400,
                  }}>{r.lift.toFixed(3)}</td>
                  <td>{r.leverage.toFixed(3)}</td>
                  <td>{r.conviction >= 999 ? "∞" : r.conviction.toFixed(3)}</td>
                  <td>
                    <div className="bar-wrap">
                      <div className="bar-bg">
                        <div className="bar-fill"
                             style={{ width: (r.score / maxScore * 100).toFixed(1) + "%" }}>
                        </div>
                      </div>
                      <strong style={{ fontSize: ".78rem" }}>{r.score.toFixed(3)}</strong>
                    </div>
                  </td>
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
        <h1>Homepage Ranking</h1>
        <p>Product ranking by basket popularity — what customers see first on the homepage</p>
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
        <h1>Frequently Bought Together</h1>
        <p>2-item and 3-item bundles ranked by co-purchase support</p>
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
  useEffect(() => {
    if (allItems.length && !selected) setSelected(allItems[0]);
  }, [allItems]);

  if (!d) return <div className="loader"><span className="spinner"></span>Loading…</div>;
  const recs = (d.cross_sell[selected] || []).slice(0, 6);

  return (
    <div>
      <div className="page-heading">
        <div className="accent-bar"></div>
        <h1>Cross-Sell Widget</h1>
        <p>Select an item added to cart — see what the ML model recommends next</p>
      </div>
      <div className="card">
        <div className="card-head"><h3>Add to Cart Simulator</h3></div>
        <select className="cs-select" value={selected} onChange={e => setSelected(e.target.value)}>
          {allItems.map(i => (
            <option key={i} value={i}>{i}</option>
          ))}
        </select>
        <div className="cs-result">
          {recs.length === 0
            ? <div className="empty">No cross-sell rules for <strong>{selected}</strong> at this threshold.</div>
            : recs.map((r, i) => (
              <div key={i} className="cs-row">
                <div className="cs-row-num">{i + 1}</div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: ".7rem", color: "#aaa", marginBottom: 3,
                    textTransform: "uppercase", letterSpacing: ".05em" }}>Also recommend</div>
                  <div className="cs-row-items">
                    {r.items.map((it, idx) => (
                      <span key={it} style={{ marginRight: 8 }}>
                        {idx > 0 && <span style={{ color: "#ccc", marginRight: 8 }}>·</span>}
                        {it}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="cs-row-meta">
                  Conf: <strong>{(r.confidence * 100).toFixed(0)}%</strong><br/>
                  Lift: <strong>{r.lift.toFixed(2)}</strong><br/>
                  Score: <strong>{r.score.toFixed(3)}</strong>
                </div>
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
        <h1>Promo Suggestions</h1>
        <p>Auto-generated promotions derived from frequent co-purchase patterns</p>
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
        <h1>Business Insights</h1>
        <p>Shelf placement, power items, and upsell opportunities — derived from your transaction data</p>
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
    <div>
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
