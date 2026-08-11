// Монтажная: тонкий клиент. Вся логика сборки живёт на сервере,
// страница только ставит задачу и рисует её состояние.

const $ = (id) => document.getElementById(id);

const state = {
  steps: [],
  duration: 30,
  jobId: null,
  timer: null,
  library: [],
  // Очередь — это id задач, уже поставленных на сервере. Страница за ними только
  // наблюдает, поэтому её можно закрыть и вернуться: сборка идёт своим ходом.
  queue: [],
  queueTotal: 0,
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
    .map((v) => `<option value="${v.id}"${v.id === "baya" ? " selected" : ""}>${v.id} · ${v.engine}</option>`)
    .join("");

  if (cfg.demo) showDemoBanner();

  drawTransport(-1, "queued");
  await loadLibrary();

  // Ссылка вида /?job=abc123 открывает конкретную сборку — удобно делиться.
  const wanted = new URLSearchParams(location.search).get("job");
  if (wanted) {
    const job = await fetch(`/api/jobs/${wanted}`).then((r) => r.json());
    if (job && job.id) render(job);
    return;
  }

  await resumeQueue();
}

async function resumeQueue() {
  // Сервер продолжает собирать, даже когда страницу закрыли. Вернувшись,
  // подхватываем недоделанное, иначе окно врёт, что работы нет.
  const { jobs } = await fetch("/api/jobs").then((r) => r.json());
  const pending = jobs
    .filter((j) => j.status === "queued" || j.status === "running")
    .map((j) => j.id)
    .reverse(); // список приходит от новых к старым, а собираются они наоборот

  if (!pending.length) return;
  state.queue = pending;
  state.queueTotal = pending.length;
  $("go").disabled = true;
  $("go").textContent = "Идёт сборка…";
  watchNext();
}

function showDemoBanner() {
  state.demo = true;
  const el = $("demo-banner");
  el.className = "banner";
  el.hidden = false;
  el.innerHTML = `<b>Витрина</b>
    Здесь можно рассмотреть интерфейс и готовые ролики, но собрать новый нельзя:
    одна сборка занимает минуту процессорного времени и полтора гигабайта памяти
    под модель озвучки. Бесплатный хостинг такого не выдержит.
    Ролики ниже собраны на локальной машине той же командой
    <code>python -m app.render_cli "тема"</code>.`;

  $("go").disabled = true;
  $("go").textContent = "Сборка недоступна";
  $("topic").disabled = true;
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

function drawQueue() {
  const left = state.queue.length;
  $("queue-info").textContent =
    state.queueTotal > 1 && left
      ? `ролик ${state.queueTotal - left + 1} из ${state.queueTotal}`
      : "";
}

function watchNext() {
  if (state.timer) {
    clearInterval(state.timer);
    state.timer = null;
  }
  if (!state.queue.length) {
    $("go").disabled = false;
    $("go").textContent = "Собрать ролики";
    state.queueTotal = 0;
    drawQueue();
    return;
  }
  state.jobId = state.queue[0];
  state.timer = setInterval(poll, 1500);
  poll();
}

async function poll() {
  const job = await fetch(`/api/jobs/${state.jobId}`).then((r) => r.json());
  render(job);
  drawQueue();
  if (job.status === "done" || job.status === "failed") {
    state.queue.shift();
    await loadLibrary();
    watchNext();
  }
}

async function loadLibrary() {
  // Читаем с диска, а не из памяти сервера: перезапуск не должен стирать полку.
  const { items } = await fetch("/api/library").then((r) => r.json());

  // Подсказка для поля папки: то, что уже есть на диске. Так темы не расползаются
  // по десятку папок с почти одинаковыми названиями.
  const folders = [...new Set(items.map((m) => m.video.split("/")[0])
    .filter((f) => f && f.endsWith(".mp4") === false))].sort();
  $("folders").innerHTML = folders.map((f) => `<option value="${f}">`).join("");

  const box = $("library");
  if (!items.length) {
    box.innerHTML = `<p class="empty">Пока пусто. Соберите первый ролик.</p>`;
    return;
  }
  state.library = items;
  box.innerHTML = `<div class="grid">${items
    .map(
      // #t=1 заставляет браузер показать кадр с первой секунды,
      // иначе карточка остаётся чёрным прямоугольником до нажатия.
      (m, i) => `<button class="card" data-i="${i}">
        <video src="/videos/${m.video}#t=1" preload="metadata" muted></video>
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
  const topics = $("topic").value
    .split("\n")
    .map((s) => s.trim())
    .filter((s) => s.length >= 3);
  if (!topics.length) return;

  $("go").disabled = true;
  $("go").textContent = "Ставлю в очередь…";

  // Ставим на сервер сразу все темы: тогда очередь переживёт закрытие вкладки.
  const ids = [];
  for (const topic of topics) {
    const job = await fetch("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        topic,
        duration: state.duration,
        voice: $("voice").value,
        music: $("music").checked,
        fresh: $("fresh").checked,
        folder: $("folder").value.trim(),
      }),
    }).then((r) => r.json());
    if (job.id) ids.push(job.id);
  }

  state.queue = ids;
  state.queueTotal = ids.length;
  $("go").textContent = "Идёт сборка…";
  watchNext();
});

boot();
