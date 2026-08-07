// Монтажная: тонкий клиент. Вся логика сборки живёт на сервере,
// страница только ставит задачу и рисует её состояние.

const $ = (id) => document.getElementById(id);

const state = {
  steps: [],
  duration: 30,
  jobId: null,
  timer: null,
  library: [],
};

const fmt = (s) => {
  const m = Math.floor(s / 60);
  const rest = (s % 60).toFixed(1).padStart(4, "0");
  return `${m}:${rest}`;
};

async function boot() {
  const cfg = await fetch("/api/config").then((r) => r.json());
  state.steps = cfg.steps;

  $("durations").innerHTML = cfg.durations
    .map((d) => `<button type="button" data-d="${d}" aria-pressed="${d === 30}">${d} с</button>`)
    .join("");
  $("durations").addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    state.duration = Number(btn.dataset.d);
    [...$("durations").children].forEach((b) =>
      b.setAttribute("aria-pressed", b === btn));
  });

  $("voice").innerHTML = cfg.voices
    .map((v) => `<option value="${v.id}"${v.id === "xenia" ? " selected" : ""}>${v.id} · ${v.engine}</option>`)
    .join("");

  drawTransport(-1, "queued");
  await loadLibrary();

  // Ссылка вида /?job=abc123 открывает конкретную сборку — удобно делиться.
  const wanted = new URLSearchParams(location.search).get("job");
  if (wanted) {
    const job = await fetch(`/api/jobs/${wanted}`).then((r) => r.json());
    if (job && job.id) render(job);
  }
}

function drawTransport(activeIndex, status) {
  $("transport").innerHTML = state.steps
    .map((s, i) => {
      let cls = "";
      if (i < activeIndex || (status === "done" && i <= activeIndex)) cls = "done";
      else if (i === activeIndex && status !== "done") cls = "active";
      return `<div class="stage ${cls}"><div class="bar"><i></i></div>
              <div class="name">${s.label}</div></div>`;
    })
    .join("");
}

function drawStatus(job) {
  const line = $("status");
  line.className = "status-line " + (job ? job.status : "");
  const texts = {
    queued: "В очереди",
    running: "Идёт сборка",
    done: "Готово",
    failed: "Не собралось",
  };
  $("status-text").textContent = job ? texts[job.status] : "Простой";
  $("status-detail").textContent = job && job.status === "running" ? job.detail : "";
}

function drawStrip(scenes) {
  const total = scenes.reduce((a, s) => a + s.seconds, 0) || 1;
  let acc = 0;
  const marks = scenes.map((s) => {
    const at = acc;
    acc += s.seconds;
    return `<span style="left:${(at / total) * 100}%">${at.toFixed(1)}</span>`;
  });

  const blocks = scenes.map((s, i) => {
    const bg = s.poster ? `background-image:url('${s.poster}')` : "";
    return `<div class="block" style="flex:${s.seconds} 1 0;${bg}">
      <span class="num">${String(i + 1).padStart(2, "0")}</span>
      <div class="meta">
        <div class="tc">${s.seconds.toFixed(1)} с</div>
        <div class="cap" title="${s.text.replace(/"/g, "&quot;")}">${s.caption || s.text}</div>
      </div></div>`;
  });

  return `<div class="strip-wrap">
    <div class="ruler">${marks.join("")}<span style="left:100%">${total.toFixed(1)}</span></div>
    <div class="strip">${blocks.join("")}</div>
  </div>`;
}

function drawResult(job) {
  const r = job.result;
  const facts = [
    `${r.seconds} с`,
    `${r.size_mb} МБ`,
    `голос ${r.voice}`,
    `собрано за ${r.elapsed} с`,
  ].map((t) => `<span class="chip">${t}</span>`).join("");

  return `<div class="result">
    <video src="/videos/${r.video}" controls preload="metadata"></video>
    <div>
      <h3>${r.title}</h3>
      <p class="hook">${r.hook}</p>
      <div class="facts">${facts}</div>
      <div class="tags">${(r.hashtags || []).join("  ")}</div>
      <div class="credits">
        Видео: Pexels / Pixabay — ${r.authors.join(", ") || "—"}<br>
        ${r.music ? "Музыка: " + r.music : "Без музыки"}
      </div>
    </div>
  </div>`;
}

function render(job) {
  drawTransport(job.step_index, job.status);
  drawStatus(job);

  const area = $("stage-area");
  let html = "";
  if (job.status === "failed") {
    html = `<div class="err"><b>Сборка остановилась.</b><br>${job.error}</div>`;
  }
  if (job.scenes && job.scenes.length) html += drawStrip(job.scenes);
  if (job.status === "done" && job.result) html += drawResult(job);
  if (!html) {
    html = `<p class="empty">Собираю: ${job.topic}. Лента сцен появится,
            когда озвучка задаст их длительность.</p>`;
  }
  area.innerHTML = html;
}

async function poll() {
  const job = await fetch(`/api/jobs/${state.jobId}`).then((r) => r.json());
  render(job);
  if (job.status === "done" || job.status === "failed") {
    clearInterval(state.timer);
    state.timer = null;
    $("go").disabled = false;
    $("go").textContent = "Собрать ролик";
    loadLibrary();
  }
}

async function loadLibrary() {
  // Читаем с диска, а не из памяти сервера: перезапуск не должен стирать полку.
  const { items } = await fetch("/api/library").then((r) => r.json());
  const box = $("library");
  if (!items.length) {
    box.innerHTML = `<p class="empty">Пока пусто. Соберите первый ролик.</p>`;
    return;
  }
  state.library = items;
  box.innerHTML = `<div class="grid">${items
    .map(
      (m, i) => `<button class="card" data-i="${i}">
        <video src="/videos/${m.video}" preload="metadata" muted></video>
        <div class="label"><b>${m.title}</b>
        <span>${m.seconds} с · ${m.voice}</span></div>
      </button>`
    )
    .join("")}</div>`;

  box.querySelectorAll(".card").forEach((card) => {
    card.addEventListener("click", () => {
      const meta = state.library[Number(card.dataset.i)];
      render({
        status: "done",
        step_index: state.steps.length - 1,
        topic: meta.topic,
        scenes: meta.scenes,
        result: meta,
      });
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });
}

$("order").addEventListener("submit", async (e) => {
  e.preventDefault();
  const topic = $("topic").value.trim();
  if (topic.length < 3) return;

  $("go").disabled = true;
  $("go").textContent = "Собираю…";

  const job = await fetch("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      topic,
      duration: state.duration,
      voice: $("voice").value,
      music: $("music").checked,
      fresh: $("fresh").checked,
    }),
  }).then((r) => r.json());

  state.jobId = job.id;
  render(job);
  state.timer = setInterval(poll, 1500);
});

boot();
