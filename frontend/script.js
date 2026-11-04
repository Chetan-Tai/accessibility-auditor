const photoInput = document.getElementById("photo-input");
const previewStrip = document.getElementById("preview-strip");
const runBtn = document.getElementById("run-btn");

const statusSection = document.getElementById("status-section");
const resultsSection = document.getElementById("results-section");
const errorSection = document.getElementById("error-section");
const errorText = document.getElementById("error-text");

const verdictHeading = document.getElementById("verdict-heading");
const verdictSummary = document.getElementById("verdict-summary");
const measurementStrip = document.getElementById("measurement-strip");
const galleryNote = document.getElementById("photo-gallery-note");
const photoGallery = document.getElementById("photo-gallery");
const flagsList = document.getElementById("flags-list");
const remediationBlock = document.getElementById("remediation-block");

const stageEls = {
  segmenting: document.querySelector('.stage[data-stage="segmenting"]'),
  calibrating: document.querySelector('.stage[data-stage="calibrating"]'),
  reasoning: document.querySelector('.stage[data-stage="reasoning"]'),
};
const STAGE_NUMBERS = { segmenting: "01", calibrating: "02", reasoning: "03" };

let selectedFiles = [];

photoInput.addEventListener("change", () => {
  selectedFiles = Array.from(photoInput.files);
  renderPreviews();
  runBtn.disabled = selectedFiles.length === 0;
});

function renderPreviews() {
  previewStrip.innerHTML = "";
  selectedFiles.forEach((file) => {
    const img = document.createElement("img");
    img.src = URL.createObjectURL(file);
    img.className = "h-16 w-16 object-cover ring-1 ring-zinc-800";
    img.alt = "";
    previewStrip.appendChild(img);
  });
}

runBtn.addEventListener("click", runAudit);

function resetStages() {
  Object.entries(stageEls).forEach(([key, el]) => {
    el.className = "stage flex items-baseline gap-4 border-l border-zinc-800 pl-4 text-zinc-600 transition-colors";
    el.querySelector(".stage-index").textContent = STAGE_NUMBERS[key];
  });
}

function applyStageEvent(evt) {
  const el = stageEls[evt.stage];
  if (!el) return;
  const indexEl = el.querySelector(".stage-index");
  if (evt.status === "start") {
    el.className = "stage flex items-baseline gap-4 border-l border-accent pl-4 text-zinc-50 transition-colors";
  } else if (evt.status === "done") {
    el.className = "stage flex items-baseline gap-4 border-l border-zinc-700 pl-4 text-zinc-400 transition-colors";
    indexEl.textContent = "✓";
  } else if (evt.status === "skipped") {
    el.className = "stage flex items-baseline gap-4 border-l border-zinc-800 pl-4 text-zinc-600 italic transition-colors";
    indexEl.textContent = "—";
  }
}

async function runAudit() {
  if (!selectedFiles.length) return;

  hide(resultsSection);
  hide(errorSection);
  resetStages();
  show(statusSection);
  runBtn.disabled = true;

  const formData = new FormData();
  selectedFiles.forEach((file) => formData.append("photos", file));

  try {
    const res = await fetch("/api/audit", { method: "POST", body: formData });
    if (!res.ok || !res.body) {
      const text = await res.text();
      throw new Error(`Server error (${res.status}): ${text}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let newlineIdx;
      while ((newlineIdx = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, newlineIdx).trim();
        buffer = buffer.slice(newlineIdx + 1);
        if (!line) continue;

        const evt = JSON.parse(line);
        if (evt.stage === "complete") {
          renderResults(evt);
        } else if (evt.stage === "error") {
          throw new Error(evt.message);
        } else {
          applyStageEvent(evt);
        }
      }
    }
  } catch (err) {
    errorText.textContent = `Something went wrong: ${err.message}`;
    show(errorSection);
  } finally {
    runBtn.disabled = false;
  }
}

function show(el) { el.classList.remove("hidden"); }
function hide(el) { el.classList.add("hidden"); }

const CONCEPT_CLASS = {
  door: "door",
  stairs: "stairs",
  ramp: "ramp",
  "floor obstruction": "floor-obstruction",
  handrail: "handrail",
  threshold: "threshold",
};

const VERDICT_COLOR = {
  ACCESSIBLE: "text-status-good",
  NOT_ACCESSIBLE: "text-status-bad",
  NEEDS_VERIFICATION: "text-status-warn",
};

const CONCERN_COLOR = {
  HIGH: "text-status-bad",
  LOW: "text-status-warn",
  NONE: "text-status-good",
};

function renderResults(data) {
  const { result, images } = data;
  const { survey, door_measurement, assessment } = result;

  renderVerdict(assessment);
  renderMeasurement(door_measurement);
  renderGalleryNote(door_measurement);
  renderGallery(result.photos, images, survey, door_measurement);
  renderFlags(assessment.flags);
  renderRemediation(assessment.remediation);

  show(resultsSection);
  verdictHeading.focus();
}

function formatVerdict(v) {
  return { ACCESSIBLE: "Accessible", NOT_ACCESSIBLE: "Not accessible", NEEDS_VERIFICATION: "Needs verification" }[v] || v;
}

function renderVerdict(assessment) {
  verdictHeading.className = `font-display text-4xl font-semibold leading-tight outline-none sm:text-5xl ${VERDICT_COLOR[assessment.overall_verdict] || "text-zinc-50"}`;
  verdictHeading.textContent = formatVerdict(assessment.overall_verdict);
  verdictSummary.textContent = assessment.summary;
}

function stat(label, value) {
  const wrap = document.createElement("div");
  wrap.innerHTML = `
    <div class="font-mono text-[10px] uppercase tracking-[0.15em] text-zinc-500">${label}</div>
    <div class="mt-1 font-mono text-2xl text-zinc-50">${value}</div>
  `;
  return wrap;
}

function renderMeasurement(m) {
  measurementStrip.innerHTML = "";
  if (!m || m.status !== "MEASURED") {
    const wrap = document.createElement("div");
    wrap.innerHTML = `
      <div class="font-mono text-[10px] uppercase tracking-[0.15em] text-zinc-500">Door width</div>
      <div class="mt-1 max-w-sm text-sm text-zinc-400">${escapeHtml((m && m.reason) || "No measurement available.")}</div>
    `;
    measurementStrip.appendChild(wrap);
    return;
  }
  const [low, high] = m.estimated_width_range_in;
  measurementStrip.appendChild(stat("Door estimated width", `${m.estimated_width_in} in`));
  measurementStrip.appendChild(stat("Range (&plusmn;margin of error)", `${low}&ndash;${high} in`));
  measurementStrip.appendChild(stat("ADA minimum", `${m.ada_minimum_in} in`));

  const verdictColorClass = { PASS: "text-status-good", BORDERLINE: "text-status-warn", BLOCKING: "text-status-bad" }[m.verdict] || "text-zinc-50";
  const verdictStat = document.createElement("div");
  verdictStat.innerHTML = `
    <div class="font-mono text-[10px] uppercase tracking-[0.15em] text-zinc-500">Verdict</div>
    <div class="mt-1 font-mono text-2xl ${verdictColorClass}">${m.verdict}</div>
  `;
  measurementStrip.appendChild(verdictStat);
}

function renderGalleryNote(doorMeasurement) {
  if (!doorMeasurement || doorMeasurement.ratio_tolerance === undefined) {
    galleryNote.textContent = "";
    return;
  }
  galleryNote.textContent =
    `Angle deviation measures how close each photo's calibration paper is to its true 8.5×11 shape — ` +
    `lower is more reliable. Tolerance: ≤${doorMeasurement.ratio_tolerance}. The lowest-deviation photo is used for measurement.`;
}

function renderGallery(photoPaths, images, survey, doorMeasurement) {
  photoGallery.innerHTML = "";

  const deviationByPath = {};
  ((doorMeasurement && doorMeasurement.photo_angle_deviations) || []).forEach((d) => {
    deviationByPath[d.path] = d;
  });

  photoPaths.forEach((path, idx) => {
    const frame = document.createElement("div");
    frame.className = "relative";

    const img = document.createElement("img");
    img.src = images[path];
    img.alt = `Photo ${idx + 1} of the entrance`;
    img.className = "block h-auto w-full ring-1 ring-zinc-800";
    frame.appendChild(img);

    const boxSpecs = [];

    Object.entries(survey).forEach(([concept, info]) => {
      const forThisPhoto = (info.by_photo || []).find((pb) => pb.photo === path);
      if (!forThisPhoto) return;
      forThisPhoto.boxes.forEach((box) => {
        if (!box) return;
        boxSpecs.push({ box, label: concept, cssKey: CONCEPT_CLASS[concept] || "door" });
      });
    });

    const isBest = doorMeasurement && doorMeasurement.status === "MEASURED" && doorMeasurement.best_photo === path;

    if (isBest && doorMeasurement.best_photo_door_box && doorMeasurement.best_photo_paper_box) {
      boxSpecs.push({ box: doorMeasurement.best_photo_door_box, label: "door — measured", cssKey: "door" });
      boxSpecs.push({ box: doorMeasurement.best_photo_paper_box, label: "calibration paper", cssKey: "paper" });
    }

    const overlayEls = boxSpecs.map((spec) => makeBoxEl(spec.label, spec.cssKey));
    overlayEls.forEach((el) => frame.appendChild(el));

    function positionOverlays() {
      const w = img.clientWidth;
      const h = img.clientHeight;
      if (!w || !h) return;
      boxSpecs.forEach((spec, i) => {
        const el = overlayEls[i];
        el.style.left = `${(spec.box.left_pct / 100) * w}px`;
        el.style.top = `${(spec.box.top_pct / 100) * h}px`;
        el.style.width = `${((spec.box.right_pct - spec.box.left_pct) / 100) * w}px`;
        el.style.height = `${((spec.box.bottom_pct - spec.box.top_pct) / 100) * h}px`;
      });
    }

    if (img.complete) {
      positionOverlays();
    } else {
      img.addEventListener("load", positionOverlays);
    }
    window.addEventListener("resize", positionOverlays);

    const caption = document.createElement("div");
    caption.className = "mt-2 font-mono text-[11px] leading-relaxed text-zinc-600";

    let captionHtml = `Photo ${idx + 1}`;
    const dev = deviationByPath[path];
    if (dev) {
      const devText = dev.deviation === null ? "no calibration paper detected" : `angle deviation ${dev.deviation}`;
      const devColor = isBest ? "text-status-good" : dev.valid ? "text-zinc-500" : "text-zinc-700";
      captionHtml += `<br><span class="${devColor}">${devText}${isBest ? " — closest, used for measurement" : ""}</span>`;
    } else if (isBest) {
      captionHtml += `<br><span class="text-status-good">used for measurement</span>`;
    }
    caption.innerHTML = captionHtml;
    frame.appendChild(caption);

    photoGallery.appendChild(frame);
  });
}

function makeBoxEl(label, cssKey) {
  const el = document.createElement("div");
  el.className = `box-overlay box-${cssKey}`;
  el.setAttribute("aria-hidden", "true");

  const labelEl = document.createElement("span");
  labelEl.className = "box-label";
  labelEl.textContent = label;
  el.appendChild(labelEl);

  return el;
}

function renderFlags(flags) {
  flagsList.innerHTML = "";
  (flags || []).forEach((flag) => {
    const details = document.createElement("details");
    details.className = "group py-4";
    details.innerHTML = `
      <summary class="flex cursor-pointer list-none items-center justify-between gap-6 [&::-webkit-details-marker]:hidden">
        <span class="text-sm font-medium text-zinc-100">${escapeHtml(flag.feature)}</span>
        <span class="flex shrink-0 items-center gap-3">
          <span class="whitespace-nowrap font-mono text-[10px] uppercase tracking-[0.15em] ${CONCERN_COLOR[flag.concern_level] || "text-zinc-500"}">${flag.concern_level}</span>
          <span class="font-mono text-sm text-zinc-600 transition-transform duration-150 group-open:rotate-45">+</span>
        </span>
      </summary>
      <div class="mt-2 max-w-xl text-sm leading-relaxed text-zinc-500">${escapeHtml(flag.observation)}</div>
    `;
    flagsList.appendChild(details);
  });
}

function renderRemediation(text) {
  remediationBlock.innerHTML = `
    <div class="font-mono text-xs uppercase tracking-[0.15em] text-zinc-500">Remediation</div>
    <p class="mt-2 max-w-xl text-sm leading-relaxed text-zinc-300">${escapeHtml(text)}</p>
  `;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}