// backend/sam_test/python/static/script.js (also mirrored in frontend/script.js)
const photoInput = document.getElementById("photo-input");
const previewStrip = document.getElementById("preview-strip");
const runBtn = document.getElementById("run-btn");
const uploadText = document.getElementById("upload-text");

const statusSection = document.getElementById("status-section");
const resultsSection = document.getElementById("results-section");
const errorSection = document.getElementById("error-section");
const errorText = document.getElementById("error-text");

const verdictBanner = document.getElementById("verdict-banner");
const measurementCard = document.getElementById("measurement-card");
const photoGallery = document.getElementById("photo-gallery");
const flagsList = document.getElementById("flags-list");
const remediationCard = document.getElementById("remediation-card");

const stageEls = {
  segmenting: document.querySelector('.stage[data-stage="segmenting"]'),
  calibrating: document.querySelector('.stage[data-stage="calibrating"]'),
  reasoning: document.querySelector('.stage[data-stage="reasoning"]'),
};

let selectedFiles = [];

photoInput.addEventListener("change", () => {
  selectedFiles = Array.from(photoInput.files);
  renderPreviews();
  runBtn.disabled = selectedFiles.length === 0;
  uploadText.textContent = selectedFiles.length
    ? `${selectedFiles.length} photo(s) selected`
    : "Click to choose photos";
});

function renderPreviews() {
  previewStrip.innerHTML = "";
  selectedFiles.forEach((file) => {
    const img = document.createElement("img");
    img.src = URL.createObjectURL(file);
    previewStrip.appendChild(img);
  });
}

runBtn.addEventListener("click", runAudit);

function resetStages() {
  Object.values(stageEls).forEach((el) => el.classList.remove("active", "done", "skipped"));
}

function applyStageEvent(evt) {
  const el = stageEls[evt.stage];
  if (!el) return;
  if (evt.status === "start") {
    el.classList.add("active");
  } else if (evt.status === "done") {
    el.classList.remove("active");
    el.classList.add("done");
  } else if (evt.status === "skipped") {
    el.classList.remove("active");
    el.classList.add("skipped");
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
    hide(statusSection);
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

function renderResults(data) {
  const { result, images } = data;
  const { survey, door_measurement, assessment } = result;

  renderVerdict(assessment);
  renderMeasurement(door_measurement);
  renderGallery(result.photos, images, survey, door_measurement);
  renderFlags(assessment.flags);
  renderRemediation(assessment.remediation);

  show(resultsSection);
}

function renderVerdict(assessment) {
  verdictBanner.className = `verdict-${assessment.overall_verdict}`;
  verdictBanner.innerHTML = `
    ${formatVerdict(assessment.overall_verdict)}
    <span class="verdict-summary">${escapeHtml(assessment.summary)}</span>
  `;
}

function formatVerdict(v) {
  return { ACCESSIBLE: "Accessible", NOT_ACCESSIBLE: "Not accessible", NEEDS_VERIFICATION: "Needs verification" }[v] || v;
}

function renderMeasurement(m) {
  if (!m || m.status !== "MEASURED") {
    measurementCard.innerHTML = `
      <h3>Door width measurement</h3>
      <p>${m && m.reason ? escapeHtml(m.reason) : "No measurement available."}</p>
    `;
    return;
  }
  const [low, high] = m.estimated_width_range_in;
  measurementCard.innerHTML = `
    <h3>Door width measurement</h3>
    <div class="measure-row"><span>Estimated clear width</span><span>${m.estimated_width_in} in (${low}&ndash;${high} in)</span></div>
    <div class="measure-row"><span>ADA minimum</span><span>${m.ada_minimum_in} in</span></div>
    <div class="measure-row"><span>Verdict</span><span class="pill pill-${m.verdict}">${m.verdict}</span></div>
    <div class="measure-row"><span>Photos considered / valid</span><span>${m.photos_considered} / ${m.valid_candidates}</span></div>
    <div class="measure-row"><span>Best-angle photo deviation</span><span>${m.best_photo_angle_deviation}</span></div>
  `;
}

function renderGallery(photoPaths, images, survey, doorMeasurement) {
  photoGallery.innerHTML = "";

  photoPaths.forEach((path, idx) => {
    const frame = document.createElement("div");
    frame.className = "photo-frame";
    frame.style.animationDelay = `${idx * 70}ms`;

    const img = document.createElement("img");
    img.src = images[path];
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

    if (
      doorMeasurement &&
      doorMeasurement.status === "MEASURED" &&
      doorMeasurement.best_photo === path &&
      doorMeasurement.best_photo_door_box &&
      doorMeasurement.best_photo_paper_box
    ) {
      boxSpecs.push({ box: doorMeasurement.best_photo_door_box, label: "door (measured)", cssKey: "door" });
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
    caption.className = "photo-caption";
    caption.textContent =
      doorMeasurement && doorMeasurement.best_photo === path
        ? `Photo ${idx + 1} — used for measurement (best angle)`
        : `Photo ${idx + 1}`;
    frame.appendChild(caption);

    photoGallery.appendChild(frame);
  });
}

function makeBoxEl(label, cssKey) {
  const el = document.createElement("div");
  el.className = `box-overlay box-${cssKey}`;
  // left/top/width/height are set in px by positionOverlays() once the
  // image's real rendered size is known — CSS percentages on an
  // absolutely-positioned element don't reliably resolve against an
  // auto-height container, so we compute pixels ourselves instead.

  const labelEl = document.createElement("span");
  labelEl.className = `box-label box-${cssKey}-label`;
  labelEl.textContent = label;
  el.appendChild(labelEl);

  return el;
}

function renderFlags(flags) {
  flagsList.innerHTML = "";
  (flags || []).forEach((flag, idx) => {
    const pillClass = flag.concern_level === "HIGH" ? "BLOCKING" : flag.concern_level === "LOW" ? "BORDERLINE" : "PASS";
    const card = document.createElement("div");
    card.className = `flag-card concern-${flag.concern_level}`;
    card.style.animationDelay = `${idx * 70}ms`;
    card.innerHTML = `
      <div class="flag-feature">${escapeHtml(flag.feature)} <span class="pill pill-${pillClass}">${flag.concern_level}</span></div>
      <div class="flag-observation">${escapeHtml(flag.observation)}</div>
    `;
    flagsList.appendChild(card);
  });
}

function renderRemediation(text) {
  remediationCard.innerHTML = `<h3>Remediation</h3><p>${escapeHtml(text)}</p>`;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}