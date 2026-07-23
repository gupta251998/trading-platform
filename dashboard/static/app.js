const REFRESH_MS = 15_000;

function fmt(n, decimals = 2) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return Number(n).toLocaleString(undefined, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function signClass(n) {
  if (n === null || n === undefined) return "";
  return n >= 0 ? "gain" : "loss";
}

async function fetchJSON(path) {
  const resp = await fetch(path);
  if (!resp.ok) throw new Error(`${path} -> ${resp.status}`);
  return resp.json();
}

function renderSummary(summary) {
  document.getElementById("tick-count").textContent = `cycle ${summary.tick_count ?? "—"}`;
  document.getElementById("poll-interval").textContent =
    summary.poll_interval_seconds ? `poll ${summary.poll_interval_seconds}s` : "poll —";

  document.getElementById("stat-equity").textContent = `$${fmt(summary.equity)}`;
  document.getElementById("stat-cash").textContent = `$${fmt(summary.cash)}`;

  const ret = document.getElementById("stat-return");
  ret.textContent = `${summary.total_return_pct >= 0 ? "+" : ""}${fmt(summary.total_return_pct)}%`;
  ret.className = `stat-value ${signClass(summary.total_return_pct)}`;

  document.getElementById("stat-open").textContent = summary.open_positions ?? "—";
  document.getElementById("stat-closed").textContent = summary.closed_trades ?? "—";
  document.getElementById("stat-winrate").textContent =
    summary.win_rate_pct !== undefined ? `${fmt(summary.win_rate_pct, 1)}%` : "—";
}

function renderPositions(positions) {
  const body = document.getElementById("positions-body");
  if (!positions.length) {
    body.innerHTML = `<tr class="empty-row"><td colspan="7">No open positions</td></tr>`;
    return;
  }
  body.innerHTML = positions.map(p => `
    <tr>
      <td>${p.symbol}</td>
      <td>${fmt(p.quantity, 6)}</td>
      <td>${fmt(p.avg_entry_price)}</td>
      <td>${fmt(p.current_price)}</td>
      <td>${fmt(p.stop_loss)}</td>
      <td>${fmt(p.profit_target)}</td>
      <td class="${signClass(p.unrealized_pnl)}">${p.unrealized_pnl !== null ? fmt(p.unrealized_pnl) : "—"}</td>
    </tr>
  `).join("");
}

function renderTrades(trades) {
  const body = document.getElementById("trades-body");
  if (!trades.length) {
    body.innerHTML = `<tr class="empty-row"><td colspan="5">No closed trades yet</td></tr>`;
    return;
  }
  body.innerHTML = trades.map(t => `
    <tr>
      <td>${t.symbol}</td>
      <td>${fmt(t.entry_price)}</td>
      <td>${fmt(t.exit_price)}</td>
      <td>${t.exit_reason}</td>
      <td class="${t.pnl >= 0 ? 'pnl-gain' : 'pnl-loss'}">${t.pnl >= 0 ? "+" : ""}${fmt(t.pnl)}</td>
    </tr>
  `).join("");
}

function renderTicker(statuses) {
  const track = document.getElementById("ticker-track");
  if (!statuses.length) {
    track.innerHTML = `<span class="ticker-item"><span class="ticker-symbol">waiting for first cycle…</span></span>`;
    return;
  }
  const items = statuses.map(s => `
    <span class="ticker-item">
      <span class="ticker-dot ${s.ok ? 'ok' : 'fail'}"></span>
      <span class="ticker-symbol">${s.symbol}</span>
      ${s.candidate_found ? '<span>▲ signal</span>' : (s.ok ? '<span>flat</span>' : `<span>${s.consecutive_failures}x fail</span>`)}
    </span>
  `).join("");
  // duplicate once so the marquee loops seamlessly
  track.innerHTML = items + items;
}

async function refresh() {
  try {
    const [summary, positions, trades, status] = await Promise.all([
      fetchJSON("/api/summary"),
      fetchJSON("/api/positions"),
      fetchJSON("/api/trades"),
      fetchJSON("/api/status"),
    ]);
    renderSummary(summary);
    renderPositions(positions);
    renderTrades(trades);
    renderTicker(status);
  } catch (err) {
    console.error("Dashboard refresh failed:", err);
  }
}

refresh();
setInterval(refresh, REFRESH_MS);
