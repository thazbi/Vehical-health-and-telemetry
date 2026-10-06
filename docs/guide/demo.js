const endpoints = {
  vehicle: "/api/vehicle",
  telemetry: "/api/telemetry",
  alerts: "/api/alerts",
};
const latencySamples = [];
const activities = [];
let successfulDemoCalls = 0;
let sessionCalls = 0;
let sessionFailures = 0;
let demoAttempts = 0;
let toastTimer;
let profileVehicleId = "";
let simulationRunning = false;
let simulationTimer = null;
let signalInFlight = false;

const byId = (id) => document.getElementById(id);
const statusNames = ["vehicle", "telemetry", "alerts"];

function addActivity(title, detail, requestId, status = "OK") {
  activities.unshift({
    time: new Date().toLocaleTimeString(),
    title,
    detail,
    requestId,
    status,
  });
  activities.splice(8);
  renderActivities();
}

function renderActivities() {
  const container = byId("activity-list");
  if (activities.length === 0) {
    container.innerHTML = '<div class="activity-empty">Activity appears here when the dashboard checks health or sends a sample signal.</div>';
    return;
  }
  container.innerHTML = activities.map((activity) => `
    <div class="activity-row">
      <span class="activity-time">${escapeHtml(activity.time)}</span>
      <div class="activity-copy"><strong>${escapeHtml(activity.title)}</strong><small>${escapeHtml(activity.detail)}</small></div>
      <span class="activity-code ${activity.status === "OK" ? "" : "is-error"}">${escapeHtml(activity.status)}</span>
      <code>${escapeHtml(activity.requestId || "local")}</code>
    </div>`).join("");
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
}

async function apiFetch(service, path, options = {}) {
  const started = performance.now();
  const requestId = options.requestId || `demo-${crypto.randomUUID()}`;
  const { requestId: _requestId, ...fetchOptions } = options;
  const response = await fetch(`${endpoints[service]}${path}`, {
    ...fetchOptions,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      "X-Request-ID": requestId,
      ...options.headers,
    },
  });
  const durationMs = performance.now() - started;
  sessionCalls += 1;
  latencySamples.push(durationMs);
  latencySamples.splice(12);
  drawLatencyChart();
  updateMetrics();
  const contentType = response.headers.get("Content-Type") || "";
  const body = contentType.includes("json")
    ? await response.json().catch(() => ({}))
    : await response.text();
  return { response, body, durationMs, requestId: response.headers.get("X-Request-ID") || requestId };
}

function setServiceStatus(name, healthy, description = "") {
  const pill = byId(`${name}-pill`);
  pill.classList.toggle("is-up", healthy);
  pill.classList.toggle("is-down", !healthy);
  pill.innerHTML = `<i></i> ${healthy ? "UP" : "DOWN"}`;
  const card = document.querySelector(`[data-service="${name}"]`);
  card.dataset.health = healthy ? "up" : "down";
  if (description) card.title = description;
}

async function loadServiceStatus() {
  let upCount = 0;
  for (const name of statusNames) {
    try {
      const path = name === "telemetry" ? "/health/ready" : "/health/live";
      const { response, body, requestId } = await apiFetch(name, path, { method: "GET" });
      const healthy = response.ok && body.status === "UP";
      setServiceStatus(name, healthy, JSON.stringify(body.dependencies || {}));
      if (healthy) upCount += 1;
      addActivity(`${name} health check`, healthy ? "Service returned UP" : `HTTP ${response.status}`, requestId, healthy ? "UP" : String(response.status));
    } catch (error) {
      setServiceStatus(name, false, error.message);
      addActivity(`${name} health check`, "Service could not be reached", "local", "DOWN");
    }
  }
  byId("system-state").textContent = upCount === 3 ? "ALL SYSTEMS UP" : `${upCount} / 3 SERVICES UP`;
  document.querySelector(".header-state").classList.toggle("is-up", upCount === 3);
  byId("system-light").style.background = upCount === 3 ? "#5b9a65" : "#cf674d";
  byId("start-notice").hidden = upCount === 3;
  byId("last-check").textContent = new Date().toLocaleTimeString();
  await Promise.all([loadVehicles(), loadAlerts(), loadMetrics()]);
}

async function loadVehicles() {
  try {
    const { response, body } = await apiFetch("vehicle", "/vehicles", { method: "GET" });
    if (!response.ok || !Array.isArray(body)) throw new Error("Vehicle API unavailable");
    byId("fleet-count").textContent = `${String(body.length).padStart(2, "0")} VEHICLES`;
    const select = byId("vehicle-id");
    const selectedId = select.value;
    select.innerHTML = body.map((vehicle) => `<option value="${escapeHtml(vehicle.vehicle_id)}">${escapeHtml(vehicle.vehicle_id)} · ${escapeHtml(vehicle.model)} · ${escapeHtml(vehicle.status)}</option>`).join("");
    if (body.some((vehicle) => vehicle.vehicle_id === selectedId)) select.value = selectedId;
    byId("vehicle-rows").innerHTML = body.map((vehicle) => `
      <tr class="${vehicle.vehicle_id === select.value ? "fleet-selected" : ""}"><td class="vehicle-id">${escapeHtml(vehicle.vehicle_id)}</td>
      <td>${escapeHtml(vehicle.model)}</td>
      <td><span class="vehicle-state ${vehicle.status === "MAINTENANCE" ? "maintenance" : ""}">${escapeHtml(vehicle.status)}</span> <button class="vehicle-pick" type="button" data-select-vehicle="${escapeHtml(vehicle.vehicle_id)}">Monitor</button></td></tr>`).join("");
    byId("vehicle-rows").querySelectorAll("[data-select-vehicle]").forEach((button) => {
      button.addEventListener("click", () => {
        select.value = button.dataset.selectVehicle;
        select.dispatchEvent(new Event("change"));
      });
    });
    if (profileVehicleId !== select.value) await loadVehiclePreferences();
  } catch {
    byId("fleet-count").textContent = "UNAVAILABLE";
    byId("vehicle-rows").innerHTML = '<tr><td colspan="3" class="empty-row">Vehicle Service is not responding</td></tr>';
  }
}

async function loadAlerts() {
  try {
    const vehicleId = encodeURIComponent(byId("vehicle-id").value);
    const { response, body } = await apiFetch("alerts", `/alerts?vehicle_id=${vehicleId}`, { method: "GET" });
    if (!response.ok || !Array.isArray(body)) throw new Error("Alert API unavailable");
    renderAlerts(body);
    const activeResult = await apiFetch("alerts", `/alerts/active?vehicle_id=${vehicleId}`, { method: "GET" });
    renderActiveBanner(
      activeResult.response.ok && Array.isArray(activeResult.body)
        ? activeResult.body.filter((alert) => !alert.acknowledged)
        : [],
    );
  } catch {
    byId("alert-count").textContent = "!";
    byId("alert-list").innerHTML = '<div class="empty-alert">Alert Service is not responding.</div>';
  }
}

function renderAlerts(alerts) {
  byId("alert-count").textContent = String(alerts.length);
  if (alerts.length === 0) {
    byId("alert-list").innerHTML = '<div class="empty-alert">No alerts recorded yet. Send a high sample reading to test the rules.</div>';
    return;
  }
  byId("alert-list").innerHTML = [...alerts].reverse().slice(0, 12).map((alert) => `
    <div class="alert-item ${alert.status === "cleared" ? "is-cleared" : ""}">
      <span class="alert-severity ${alert.status === "cleared" ? "cleared" : alert.acknowledged ? "acknowledged" : alert.severity === "critical" ? "critical" : ""}">${escapeHtml(alert.status === "cleared" ? "cleared" : alert.acknowledged ? "acknowledged · still active" : alert.severity)}</span>
      <div class="alert-copy"><strong>${escapeHtml(alert.rule.replaceAll("_", " "))}</strong><small>${escapeHtml(alert.vehicle_id)} · ${escapeHtml(alert.observed_value)} / limit ${escapeHtml(alert.threshold)}</small></div>
      <span class="alert-time">${new Date(alert.created_at).toLocaleTimeString()}</span>
    </div>`).join("");
}

  function renderActiveBanner(alerts) {
    const banner = byId("active-alert-banner");
    banner.hidden = alerts.length === 0;
    byId("banner-alert-count").textContent = `${alerts.length} UNACKNOWLEDGED`;
    banner.classList.toggle("is-critical", alerts.some((alert) => alert.severity === "critical"));
    if (!alerts.length) return;
    const topAlert = alerts[0];
    byId("banner-alert-state").textContent = `${topAlert.severity.toUpperCase()} · ACTIVE VEHICLE ALERT`;
    byId("banner-alert-title").textContent = `${topAlert.vehicle_id}: ${topAlert.rule.replaceAll("_", " ")}`;
    byId("banner-alert-message").textContent = `${topAlert.message}. ${topAlert.recommended_action} Alert clears after a safe reading.`;
  }

  byId("acknowledge-alerts").addEventListener("click", async () => {
    const vehicleId = encodeURIComponent(byId("vehicle-id").value);
    try {
      const activeResult = await apiFetch("alerts", `/alerts/active?vehicle_id=${vehicleId}`, { method: "GET" });
      if (!activeResult.response.ok || !Array.isArray(activeResult.body)) {
        throw new Error("Could not load active alerts");
      }
      const alertsToAcknowledge = activeResult.body.filter((alert) => !alert.acknowledged);
      await Promise.all(alertsToAcknowledge.map((alert) => apiFetch(
        "alerts",
        `/alerts/${encodeURIComponent(alert.alert_id)}/acknowledge`,
        { method: "POST" },
      )));
      await loadAlerts();
      showResult("Notice acknowledged and closed. Monitoring continues; the active condition remains in history until readings recover.", "good");
      showToast("Notice closed; monitoring continues");
    } catch (error) {
      showToast(error.message || "Could not acknowledge alert");
    }
  });

  function setPreferencesForm(preferences) {
    byId("pref-speed").value = preferences.speed_limit_kmh;
    byId("pref-speed-duration").value = preferences.speed_duration_seconds;
    byId("pref-rpm").value = preferences.rpm_limit;
    byId("pref-rpm-duration").value = preferences.rpm_duration_seconds;
    byId("pref-temperature").value = preferences.battery_temperature_limit_c;
    byId("pref-temperature-duration").value = preferences.battery_temperature_duration_seconds;
    const vehicleId = byId("vehicle-id").value;
    byId("preferences-vehicle-name").textContent = vehicleId;
    byId("threshold-hint").innerHTML = `<span>LIMITS FOR ${escapeHtml(vehicleId)}</span><b>Speed ${escapeHtml(preferences.speed_limit_kmh)} km/h</b><b>RPM ${escapeHtml(preferences.rpm_limit)}</b><b>Battery ${escapeHtml(preferences.battery_temperature_limit_c)}°C</b>`;
  }

  async function loadVehiclePreferences() {
    const vehicleId = byId("vehicle-id").value;
    if (!vehicleId) return;
    profileVehicleId = vehicleId;
    try {
      const { response, body } = await apiFetch("vehicle", `/vehicles/${encodeURIComponent(vehicleId)}`, { method: "GET" });
      if (!response.ok) throw new Error("Vehicle settings could not be loaded");
      setPreferencesForm(body.preferences || {});
      byId("profile-feedback").textContent = `Loaded limits for ${vehicleId}.`;
      byId("profile-feedback").classList.remove("is-error");
    } catch (error) {
      byId("profile-feedback").textContent = error.message;
      byId("profile-feedback").classList.add("is-error");
    }
  }

  function readPreferencesForm() {
    return {
      speed_limit_kmh: Number(byId("pref-speed").value),
      speed_duration_seconds: Number(byId("pref-speed-duration").value),
      rpm_limit: Number(byId("pref-rpm").value),
      rpm_duration_seconds: Number(byId("pref-rpm-duration").value),
      battery_temperature_limit_c: Number(byId("pref-temperature").value),
      battery_temperature_duration_seconds: Number(byId("pref-temperature-duration").value),
    };
  }

function parsePrometheus(text) {
  const values = { calls: 0, failures: 0 };
  for (const line of text.split("\n")) {
    if (line.startsWith("#") || !line.trim()) continue;
    const match = line.match(/^(http_requests_total|http_requests_failed_total)(?:\{[^}]*\})?\s+([\d.eE+-]+)/);
    if (!match) continue;
    const value = Number(match[2]);
    if (!Number.isFinite(value)) continue;
    if (match[1] === "http_requests_total") values.calls += value;
    else values.failures += value;
  }
  return values;
}

async function loadMetrics() {
  const all = { calls: 0, failures: 0 };
  for (const name of statusNames) {
    try {
      const { response, body } = await apiFetch(name, "/metrics", { method: "GET", headers: { Accept: "text/plain" } });
      if (!response.ok || typeof body !== "string") continue;
      const parsed = parsePrometheus(body);
      all.calls += parsed.calls;
      all.failures += parsed.failures;
    } catch {
      // Health cards already show when a metrics source is unavailable.
    }
  }
  byId("metric-calls").textContent = String(Math.round(all.calls));
  byId("metric-failures").textContent = String(Math.round(all.failures));
}

function updateMetrics(lastDuration) {
  byId("metric-latency").textContent = latencySamples.length
    ? `${latencySamples[latencySamples.length - 1].toFixed(1)} ms`
    : "—";
  byId("metric-success").textContent = demoAttempts
    ? `${Math.round((successfulDemoCalls / demoAttempts) * 100)}%`
    : "—";
  if (Number.isFinite(lastDuration)) byId("metric-latency").title = `Last end-to-end demo flow: ${lastDuration.toFixed(1)} ms`;
}

function drawLatencyChart() {
  const canvas = byId("latency-chart");
  const bounds = canvas.getBoundingClientRect();
  if (!bounds.width || !bounds.height) return;
  const scale = window.devicePixelRatio || 1;
  canvas.width = Math.round(bounds.width * scale);
  canvas.height = Math.round(bounds.height * scale);
  const context = canvas.getContext("2d");
  context.scale(scale, scale);
  byId("chart-empty").hidden = latencySamples.length > 0;
  if (latencySamples.length === 0) return;
  const max = Math.max(...latencySamples, 10) * 1.2;
  const gap = 8;
  const barWidth = Math.max(5, (bounds.width - gap * (latencySamples.length - 1)) / latencySamples.length);
  latencySamples.forEach((sample, index) => {
    const height = Math.max(3, (sample / max) * (bounds.height - 12));
    const x = index * (barWidth + gap);
    const y = bounds.height - height;
    context.fillStyle = index === latencySamples.length - 1 ? "#df7c57" : "#74a378";
    context.fillRect(x, y, barWidth, height);
  });
}

function showResult(message, type = "") {
  const result = byId("request-result");
  result.className = `request-result ${type ? `is-${type}` : ""}`;
  result.innerHTML = `<span class="result-mark">${type === "good" ? "✓" : type === "error" ? "!" : "—"}</span><span>${escapeHtml(message)}</span>`;
}

function showToast(message) {
  const toast = byId("demo-toast");
  toast.textContent = message;
  toast.classList.add("is-visible");
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => toast.classList.remove("is-visible"), 2100);
}

async function sendSignal() {
  if (signalInFlight) return;
  const form = byId("signal-form");
  if (!form.reportValidity()) return;
  signalInFlight = true;
  const button = byId("submit-button");
  const payload = {
    vehicle_id: byId("vehicle-id").value,
    speed: Number(byId("speed").value),
    rpm: Number(byId("rpm").value),
    battery_temperature: Number(byId("temperature").value),
  };
  button.disabled = true;
  button.querySelector("span:nth-child(2)").textContent = simulationRunning ? "Simulation sending…" : "Sending signal…";
  demoAttempts += 1;
  const requestId = `demo-${crypto.randomUUID()}`;
  const flowStart = performance.now();
  try {
    const telemetry = await apiFetch("telemetry", "/telemetry", {
      method: "POST",
      requestId,
      body: JSON.stringify(payload),
    });
    if (!telemetry.response.ok) {
      sessionFailures += 1;
      updateMetrics();
      const message = telemetry.body.message || telemetry.body.detail?.message || `Telemetry rejected (HTTP ${telemetry.response.status})`;
      showResult(message, "error");
      addActivity("Telemetry rejected", message, telemetry.requestId, String(telemetry.response.status));
      showToast(`Telemetry returned HTTP ${telemetry.response.status}`);
      return;
    }
    byId("latest-reading-values").textContent = `${payload.vehicle_id} · ${payload.speed} km/h · ${payload.rpm} RPM · ${payload.battery_temperature}°C`;
    byId("latest-reading-time").textContent = `Accepted at ${new Date().toLocaleTimeString()}`;

    const alertResult = await apiFetch("alerts", "/alerts/evaluate", {
      method: "POST",
      requestId,
      body: JSON.stringify(payload),
    });
    const flowDuration = performance.now() - flowStart;
    if (!alertResult.response.ok) {
      sessionFailures += 1;
      updateMetrics(flowDuration);
      showResult("Telemetry stored, but alert evaluation failed.", "error");
      addActivity("Alert evaluation failed", `HTTP ${alertResult.response.status}`, requestId, String(alertResult.response.status));
      showToast("Telemetry accepted; alert call failed");
      await loadAlerts();
      return;
    }

    successfulDemoCalls += 1;
    updateMetrics(flowDuration);
    const result = alertResult.body;
    const activeAlerts = result.active_alerts || [];
    const newAlerts = result.new_alerts || [];
    const clearedAlerts = result.cleared_alerts || [];
    const pendingConditions = result.pending_conditions || [];
    renderActiveBanner(activeAlerts);
    renderPendingConditions(pendingConditions);
    if (clearedAlerts.length) {
      showResult(`${clearedAlerts.length} alert condition cleared. The reading is back below its configured limit.`, "good");
      showToast("Condition returned to safe range; active alert cleared");
    } else if (newAlerts.length) {
      showResult(`${newAlerts.length} alert${newAlerts.length === 1 ? "" : "s"} active. ${newAlerts[0].message}.`, "error");
      showToast(`${newAlerts.length} vehicle alert(s) now active`);
    } else if (pendingConditions.length) {
      showResult(`${pendingConditions.length} condition(s) above limit; waiting for the configured persistence duration.`, "");
    } else if (activeAlerts.length) {
      showResult(`${activeAlerts.length} active alert(s). Reduce the reading below its saved limit to clear.`, "error");
    } else {
      showResult(`Reading accepted. All values are within this vehicle's configured limits. ${flowDuration.toFixed(1)} ms.`, "good");
    }
    addActivity("Signal evaluated", `${payload.vehicle_id} · ${payload.speed} km/h · ${activeAlerts.length} active · ${pendingConditions.length} pending · ${flowDuration.toFixed(1)} ms`, requestId, "201 / OK");
    await Promise.all([loadVehicles(), loadAlerts(), loadMetrics()]);
  } catch (error) {
    sessionFailures += 1;
    updateMetrics();
    showResult("Could not reach the local APIs. Start the project with START-DEMO.bat.", "error");
    addActivity("Demo request failed", error.message, requestId, "OFFLINE");
    byId("start-notice").hidden = false;
    showToast("Local services are offline");
  } finally {
    button.disabled = false;
    button.querySelector("span:nth-child(2)").textContent = "Send one reading";
    signalInFlight = false;
  }
}

function renderPendingConditions(conditions) {
  const list = byId("pending-list");
  list.innerHTML = conditions.map((condition) => `
    <div class="pending-condition"><strong>${escapeHtml(condition.rule.replaceAll("_", " "))} · ${escapeHtml(condition.observed_value)} / ${escapeHtml(condition.threshold)}</strong><small>Above limit for ${escapeHtml(condition.elapsed_seconds)}s · alert after ${escapeHtml(condition.duration_seconds)}s</small><b>${escapeHtml(condition.remaining_seconds)}s left</b></div>`).join("");
}

byId("signal-form").addEventListener("submit", (event) => {
  event.preventDefault();
  sendSignal();
});

byId("vehicle-id").addEventListener("change", async () => {
  await loadVehiclePreferences();
  await loadAlerts();
});

byId("preferences-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const vehicleId = byId("vehicle-id").value;
  try {
    const { response, body } = await apiFetch("vehicle", `/vehicles/${encodeURIComponent(vehicleId)}/preferences`, {
      method: "PUT",
      body: JSON.stringify(readPreferencesForm()),
    });
    if (!response.ok) throw new Error(body.detail || "Preferences could not be saved");
    setPreferencesForm(body.preferences);
    byId("profile-feedback").textContent = `Saved monitoring limits for ${vehicleId}. New readings will use these preferences.`;
    byId("profile-feedback").classList.remove("is-error");
    addActivity("Vehicle limits saved", vehicleId, response.headers.get("X-Request-ID"), "SAVED");
    showToast("Vehicle monitoring limits saved");
  } catch (error) {
    byId("profile-feedback").textContent = error.message;
    byId("profile-feedback").classList.add("is-error");
  }
});

byId("register-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const feedback = byId("profile-feedback");
  try {
    const { response, body } = await apiFetch("vehicle", "/vehicles", {
      method: "POST",
      body: JSON.stringify({
        vehicle_id: byId("new-vehicle-id").value.trim(),
        model: byId("new-vehicle-model").value.trim(),
        status: "ACTIVE",
        preferences: readPreferencesForm(),
      }),
    });
    if (!response.ok) throw new Error(body.detail || "Vehicle could not be registered");
    feedback.textContent = `Registered ${body.vehicle_id}. It is ready for monitoring.`;
    feedback.classList.remove("is-error");
    byId("register-form").reset();
    await loadVehicles();
    byId("vehicle-id").value = body.vehicle_id;
    await loadVehiclePreferences();
    addActivity("Vehicle registered", `${body.vehicle_id} · ${body.model}`, response.headers.get("X-Request-ID"), "201");
    showToast(`${body.vehicle_id} added to this local fleet`);
  } catch (error) {
    feedback.textContent = error.message;
    feedback.classList.add("is-error");
  }
});

byId("simulate-button").addEventListener("click", async () => {
  simulationRunning = !simulationRunning;
  const button = byId("simulate-button");
  button.classList.toggle("is-running", simulationRunning);
  button.querySelector("#simulate-label").textContent = simulationRunning
    ? "Stop live simulation"
    : "Start live simulation";
  button.querySelector("span:first-child").textContent = simulationRunning ? "■" : "▶";
  if (!simulationRunning) {
    window.clearTimeout(simulationTimer);
    showToast("Synthetic telemetry simulation stopped");
    return;
  }
  showToast("Synthetic telemetry running every 3 seconds");
  const tick = async () => {
    if (!simulationRunning) return;
    await sendSignal();
    if (simulationRunning) simulationTimer = window.setTimeout(tick, 3000);
  };
  await tick();
});

byId("refresh-button").addEventListener("click", async () => {
  byId("refresh-button").disabled = true;
  await loadServiceStatus();
  byId("refresh-button").disabled = false;
  showToast("Live service status refreshed");
});

window.addEventListener("resize", drawLatencyChart);
loadServiceStatus();
window.setInterval(loadServiceStatus, 15000);
