const COLORS = {
  primary: "#1456F0",
  red: "#E5484D",
  text: "#222222",
  muted: "#66717E",
  grid: "#EDF0F3",
  amber: "#D67D00",
};

const toNumber = (value) => {
  if (value === undefined || value === null || value === "") return null;
  const parsed = Number(String(value).replaceAll(",", ""));
  return Number.isFinite(parsed) ? parsed : null;
};

function parseCsv(text) {
  const lines = text.trim().split(/\r?\n/).filter(Boolean);
  if (lines.length < 2) return [];
  const headers = lines[0].split(",");
  return lines.slice(1).map((line) => {
    const values = line.split(",");
    return Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""]));
  });
}

function formatMoney(value, unit = "억") {
  const number = toNumber(value);
  if (number === null) return "—";
  const divisor = unit === "조" ? 1e12 : 1e8;
  const converted = number / divisor;
  return `${converted > 0 ? "+" : ""}${converted.toLocaleString("ko-KR", {
    minimumFractionDigits: unit === "조" ? 1 : 0,
    maximumFractionDigits: unit === "조" ? 1 : 0,
  })}${unit}`;
}

function formatPoint(value, suffix = "pt") {
  const number = toNumber(value);
  if (number === null) return "—";
  return `${number > 0 ? "+" : ""}${number.toFixed(2)}${suffix}`;
}

function setSignedClass(element, value) {
  const number = toNumber(value);
  element.classList.remove("value-positive", "value-negative");
  if (number > 0) element.classList.add("value-positive");
  if (number < 0) element.classList.add("value-negative");
}

function getBadge(row) {
  const basis = toNumber(row.basis);
  const theoretical = toNumber(row.theoretical_basis);
  if (basis === null) return { text: "데이터 확인 필요", className: "neutral" };
  if (basis < 0) return { text: "🔻백워데이션", className: "backwardation" };
  if (theoretical !== null && basis - theoretical >= 2) {
    return { text: "⚠️콘탱고 과열", className: "hot" };
  }
  return { text: "정상권", className: "normal" };
}

function renderSummary(row) {
  const date = new Date(`${row.date}T00:00:00+09:00`);
  document.querySelector("#latest-date").textContent = `${new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "long",
    day: "numeric",
  }).format(date)} 마감`;

  const spot = document.querySelector("#spot-value");
  spot.textContent = formatMoney(row.foreign);
  setSignedClass(spot, row.foreign);
  document.querySelector("#spot-sub").textContent = `20일 누적 ${formatMoney(row.foreign_spot_20d, "조")}`;

  const futures = document.querySelector("#futures-flow-value");
  futures.textContent = formatMoney(row.foreign_futures);
  setSignedClass(futures, row.foreign_futures);
  document.querySelector("#futures-flow-sub").textContent = `20일 누적 ${formatMoney(row.foreign_futures_20d, "조")}`;

  const basis = document.querySelector("#basis-value");
  basis.textContent = formatPoint(row.basis);
  setSignedClass(basis, row.basis);
  document.querySelector("#basis-sub").textContent = `이론 ${formatPoint(row.theoretical_basis)}`;

  const gap = document.querySelector("#gap-value");
  gap.textContent = formatPoint(row.basis_gap_pct, "%");
  setSignedClass(gap, row.basis_gap_pct);
  const badge = getBadge(row);
  const badgeElement = document.querySelector("#basis-badge");
  badgeElement.textContent = badge.text;
  badgeElement.className = `badge ${badge.className}`;
  document.querySelector("#source-label").textContent =
    String(row.fallback_used).toLowerCase() === "true" ? "pykrx · NAVER 폴백" : "KRX · pykrx";
}

function axisLayout(title = "") {
  return {
    title: { text: title, font: { size: 11, color: COLORS.muted }, standoff: 8 },
    gridcolor: COLORS.grid,
    zerolinecolor: "#AAB2BC",
    tickfont: { size: 10, color: COLORS.muted },
    fixedrange: true,
  };
}

function baseLayout() {
  return {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    margin: { l: 52, r: 22, t: 30, b: 48 },
    font: { family: "Pretendard, sans-serif", color: COLORS.text },
    hovermode: "x unified",
    hoverlabel: { bgcolor: "#FFFFFF", bordercolor: "#DDE2E8", font: { color: COLORS.text } },
    legend: { orientation: "h", y: 1.12, x: 0, font: { size: 10, color: COLORS.muted } },
    xaxis: { ...axisLayout(), showgrid: false, rangeslider: { visible: false } },
    yaxis: axisLayout("억원"),
    bargap: 0.25,
  };
}

function barColors(values) {
  return values.map((value) => (value !== null && value < 0 ? COLORS.primary : COLORS.red));
}

function renderCharts(rows) {
  const dates = rows.map((row) => row.date);
  const spot = rows.map((row) => (toNumber(row.foreign) ?? 0) / 1e8);
  const spot20 = rows.map((row) => (toNumber(row.foreign_spot_20d) ?? 0) / 1e8);
  const futures = rows.map((row) => (toNumber(row.foreign_futures) ?? 0) / 1e8);
  const openInterest = rows.map((row) => toNumber(row.open_interest));
  const basis = rows.map((row) => toNumber(row.basis));
  const theoretical = rows.map((row) => toNumber(row.theoretical_basis));
  const finance = rows.map((row) => (toNumber(row.financial_investment) ?? 0) / 1e8);
  const plotConfig = { responsive: true, displayModeBar: false, scrollZoom: false };

  Plotly.newPlot(
    "spot-chart",
    [
      {
        x: dates,
        y: spot,
        type: "bar",
        name: "일별 순매수",
        marker: { color: barColors(spot), line: { width: 0 } },
        hovertemplate: "%{y:+,.0f}억<extra></extra>",
      },
      {
        x: dates,
        y: spot20,
        type: "scatter",
        mode: "lines",
        name: "20일 누적",
        line: { color: "#252A34", width: 2.4 },
        hovertemplate: "%{y:+,.0f}억<extra></extra>",
      },
    ],
    baseLayout(),
    plotConfig,
  );

  const futuresLayout = baseLayout();
  futuresLayout.margin.r = 52;
  futuresLayout.yaxis2 = {
    ...axisLayout("계약"),
    overlaying: "y",
    side: "right",
    showgrid: false,
  };
  Plotly.newPlot(
    "futures-chart",
    [
      {
        x: dates,
        y: futures,
        type: "bar",
        name: "외국인 선물",
        marker: { color: barColors(futures), line: { width: 0 } },
        hovertemplate: "%{y:+,.0f}억<extra></extra>",
      },
      {
        x: dates,
        y: openInterest,
        type: "scatter",
        mode: "lines",
        yaxis: "y2",
        name: "미결제약정",
        connectgaps: false,
        line: { color: COLORS.amber, width: 2.2 },
        hovertemplate: "%{y:,.0f}계약<extra></extra>",
      },
    ],
    futuresLayout,
    plotConfig,
  );

  const basisLayout = baseLayout();
  basisLayout.yaxis.title.text = "포인트";
  basisLayout.shapes = dates
    .map((day, index) => ({ day, value: basis[index], next: dates[index + 1] || day }))
    .filter((item) => item.value !== null && item.value < 0)
    .map((item) => ({
      type: "rect",
      xref: "x",
      yref: "paper",
      x0: item.day,
      x1: item.next,
      y0: 0,
      y1: 1,
      fillcolor: "rgba(20, 86, 240, 0.08)",
      line: { width: 0 },
      layer: "below",
    }));
  basisLayout.shapes.push({
    type: "line",
    xref: "paper",
    x0: 0,
    x1: 1,
    y0: 0,
    y1: 0,
    line: { color: "#8C96A3", width: 1, dash: "dot" },
  });
  Plotly.newPlot(
    "basis-chart",
    [
      {
        x: dates,
        y: basis,
        type: "scatter",
        mode: "lines",
        name: "실제 베이시스",
        connectgaps: false,
        line: { color: COLORS.primary, width: 2.7 },
        hovertemplate: "%{y:+.2f}pt<extra></extra>",
      },
      {
        x: dates,
        y: theoretical,
        type: "scatter",
        mode: "lines",
        name: "이론 베이시스",
        connectgaps: false,
        line: { color: COLORS.amber, width: 2, dash: "dash" },
        hovertemplate: "%{y:+.2f}pt<extra></extra>",
      },
    ],
    basisLayout,
    plotConfig,
  );

  Plotly.newPlot(
    "finance-chart",
    [
      {
        x: dates,
        y: finance,
        type: "bar",
        name: "금융투자",
        marker: { color: barColors(finance), line: { width: 0 } },
        hovertemplate: "%{y:+,.0f}억<extra></extra>",
      },
    ],
    baseLayout(),
    plotConfig,
  );
}

async function init() {
  const notice = document.querySelector("#error-state");
  try {
    const response = await fetch(`data/flows.csv?v=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const rows = parseCsv(await response.text()).sort((a, b) => a.date.localeCompare(b.date));
    if (!rows.length) {
      notice.hidden = false;
      notice.textContent = "아직 수집된 데이터가 없습니다. 백필 또는 일일 수집을 실행하면 차트가 표시됩니다.";
      document.querySelector("#latest-date").textContent = "데이터 대기 중";
      return;
    }
    renderSummary(rows.at(-1));
    renderCharts(rows);
  } catch (error) {
    console.error(error);
    notice.hidden = false;
    notice.textContent = "데이터를 불러오지 못했습니다. 잠시 후 다시 확인해 주세요.";
    document.querySelector("#latest-date").textContent = "불러오기 실패";
  }
}

window.addEventListener("DOMContentLoaded", init);

