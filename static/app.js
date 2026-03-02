/* ═══════════════════════════════════════════════════════════
   Nick's Recipe Extractor — Frontend
   Simple: Login → Auto-process → Browse Recipes
   ═══════════════════════════════════════════════════════════ */

let recipes = [];
let pollTimer = null;

// ── Init ────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
    // Check if already logged in with recipes
    const res = await fetch("/api/auth-status");
    const auth = await res.json();

    if (auth.recipes_count > 0) {
        // Already have recipes, go straight to recipe view
        showScreen("recipes");
        loadRecipes();
    } else if (auth.logged_in) {
        // Logged in but no recipes yet — start processing
        showScreen("processing");
        startPipeline();
    }
    // else: show login screen (default)

    // Setup search/filter listeners
    document.getElementById("search-box").addEventListener("input", renderRecipes);
    document.getElementById("filter-cat").addEventListener("change", renderRecipes);

    // Enter key on login form
    document.getElementById("ig-password").addEventListener("keypress", e => {
        if (e.key === "Enter") doLogin();
    });
    document.getElementById("ig-2fa").addEventListener("keypress", e => {
        if (e.key === "Enter") doLogin();
    });
});


// ── Screen Management ───────────────────────────────────────
function showScreen(name) {
    document.querySelectorAll(".screen").forEach(s => s.classList.remove("active"));
    document.getElementById(`screen-${name}`).classList.add("active");
}


// ── LOGIN ───────────────────────────────────────────────────
async function doLogin() {
    const btn = document.getElementById("btn-login");
    const errEl = document.getElementById("login-error");
    errEl.classList.add("hidden");

    const username = document.getElementById("ig-username").value.trim();
    const password = document.getElementById("ig-password").value.trim();
    const twofa = document.getElementById("ig-2fa").value.trim();

    if (!username || !password) {
        showError("Enter your username and password");
        return;
    }

    btn.disabled = true;
    btn.textContent = "Logging in...";

    try {
        const res = await fetch("/api/login", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({username, password, two_factor_code: twofa}),
        });
        const data = await res.json();

        if (data.needs_2fa) {
            document.getElementById("twofa-section").classList.remove("hidden");
            showError("Enter the 2FA code from your authenticator app");
            btn.disabled = false;
            btn.textContent = "Submit 2FA Code";
            return;
        }

        if (data.error) {
            showError(data.error);
            btn.disabled = false;
            btn.textContent = "Log In & Get My Recipes";
            return;
        }

        // Success! Start the pipeline
        showScreen("processing");
        startPipeline();

    } catch (err) {
        showError("Connection error. Make sure the app is running.");
        btn.disabled = false;
        btn.textContent = "Log In & Get My Recipes";
    }
}

async function doBrowserLogin() {
    const btn = document.getElementById("btn-browser");
    const errEl = document.getElementById("login-error");
    errEl.classList.add("hidden");

    btn.disabled = true;
    btn.textContent = "🔍 Checking browser cookies...";

    try {
        const res = await fetch("/api/login-browser", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({browser: "auto"}),
        });
        const data = await res.json();

        if (data.error) {
            showError(data.error);
            btn.disabled = false;
            btn.textContent = "🌐 Use My Browser Session (Chrome/Firefox/Safari)";
            return;
        }

        // Success!
        showScreen("processing");
        startPipeline();

    } catch (err) {
        showError("Connection error. Make sure the app is running.");
        btn.disabled = false;
        btn.textContent = "🌐 Use My Browser Session (Chrome/Firefox/Safari)";
    }
}

async function doSessionIdLogin() {
    const sessionid = document.getElementById("ig-sessionid").value.trim();
    if (!sessionid) { showError("Paste your sessionid value"); return; }

    const errEl = document.getElementById("login-error");
    errEl.classList.add("hidden");

    try {
        const res = await fetch("/api/login-sessionid", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({sessionid}),
        });
        const data = await res.json();

        if (data.error) { showError(data.error); return; }

        showScreen("processing");
        startPipeline();
    } catch (err) {
        showError("Connection error.");
    }
}

function skipLogin() {
    showScreen("processing");
    startLocalProcessing();
}

function showError(msg) {
    const el = document.getElementById("login-error");
    el.textContent = msg;
    el.classList.remove("hidden");
}


// ── PROCESSING PIPELINE ────────────────────────────────────
async function startPipeline() {
    try {
        const res = await fetch("/api/fetch-and-process", {method: "POST"});
        const data = await res.json();
        if (data.error) {
            document.getElementById("progress-msg").textContent = data.error;
            return;
        }
        startPolling();
    } catch (err) {
        document.getElementById("progress-msg").textContent = "Failed to start. Check the terminal.";
    }
}

async function startLocalProcessing() {
    document.getElementById("proc-subtitle").textContent = "Processing videos already in your data/videos folder...";
    try {
        const res = await fetch("/api/process-local", {method: "POST"});
        const data = await res.json();
        if (data.error) {
            document.getElementById("progress-msg").textContent = data.error;
            return;
        }
        startPolling();
    } catch (err) {
        document.getElementById("progress-msg").textContent = "Failed to start.";
    }
}

function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(pollStatus, 1200);
}

async function pollStatus() {
    try {
        const res = await fetch("/api/status");
        const s = await res.json();

        // Update progress bar
        const fill = document.getElementById("progress-fill");
        const msg = document.getElementById("progress-msg");

        if (s.total > 0) {
            fill.style.width = `${Math.round((s.current / s.total) * 100)}%`;
        } else if (s.phase === "fetch") {
            // Indeterminate progress for fetch
            fill.style.width = "30%";
        }

        msg.textContent = s.message || "Working...";

        // Update pipeline visual
        updatePipeStep("fetch", s.phase);
        updatePipeStep("transcribe", s.phase);
        updatePipeStep("extract", s.phase);
        updatePipeStep("done", s.phase);

        // Show errors
        if (s.errors && s.errors.length > 0) {
            const errBox = document.getElementById("proc-errors");
            errBox.classList.remove("hidden");
            errBox.innerHTML = s.errors.map(e => `<p>⚠️ ${esc(e)}</p>`).join("");
        }

        // Done?
        if (!s.active && (s.phase === "done" || s.phase === "error")) {
            clearInterval(pollTimer);
            pollTimer = null;

            if (s.phase === "done") {
                fill.style.width = "100%";
                setTimeout(() => {
                    showScreen("recipes");
                    loadRecipes();
                }, 1500);
            }
        }
    } catch (err) { /* ignore */ }
}

function updatePipeStep(stepId, currentPhase) {
    const order = ["fetch", "transcribe", "extract", "done"];
    const el = document.getElementById(`pipe-${stepId}`);
    const statusEl = el.querySelector(".pipe-status");
    const stepIdx = order.indexOf(stepId);
    const currentIdx = order.indexOf(currentPhase);

    if (currentPhase === "error") {
        statusEl.textContent = "error";
        statusEl.className = "pipe-status error";
        return;
    }

    if (currentIdx > stepIdx) {
        statusEl.textContent = "done ✓";
        statusEl.className = "pipe-status done";
        el.classList.add("completed");
    } else if (currentIdx === stepIdx) {
        statusEl.textContent = "running...";
        statusEl.className = "pipe-status active";
        el.classList.add("active-step");
    } else {
        statusEl.textContent = "waiting";
        statusEl.className = "pipe-status";
    }
}


// ── RECIPES VIEW ────────────────────────────────────────────
async function loadRecipes() {
    try {
        const res = await fetch("/api/recipes");
        const data = await res.json();
        recipes = data.recipes || [];
        renderRecipes();
    } catch (err) {
        console.error(err);
    }
}

function renderRecipes() {
    const grid = document.getElementById("recipes-grid");
    const search = document.getElementById("search-box").value.toLowerCase();
    const cat = document.getElementById("filter-cat").value;

    let filtered = recipes.filter(r => {
        if (cat && r.category !== cat) return false;
        if (search) {
            const txt = `${r.title} ${r.description} ${(r.ingredients||[]).map(i=>i.item).join(" ")}`.toLowerCase();
            return txt.includes(search);
        }
        return true;
    });

    document.getElementById("recipe-count").textContent = `${filtered.length} recipe${filtered.length!==1?'s':''}`;

    if (filtered.length === 0) {
        grid.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">📭</div>
                <h3>${recipes.length === 0 ? 'No recipes yet' : 'No matches'}</h3>
                <p>${recipes.length === 0 ? 'Click Re-fetch to pull your saved Instagram recipes' : 'Try different search terms'}</p>
            </div>`;
        return;
    }

    grid.innerHTML = filtered.map((r, i) => {
        const realIdx = recipes.indexOf(r);
        const emoji = {breakfast:"🌅",lunch:"🥪",dinner:"🍽️",snack:"🍿",dessert:"🍰",side:"🥗"}[r.category]||"🍽️";
        const ingList = (r.ingredients||[]).slice(0,3).map(i=>i.item).join(", ");
        const more = (r.ingredients||[]).length - 3;

        return `
        <div class="recipe-card" onclick="openRecipe(${realIdx})">
            <button class="card-delete" onclick="event.stopPropagation();deleteRecipe(${realIdx})" title="Delete">×</button>
            <div class="card-cat">${emoji} ${r.category||'dinner'}</div>
            <h3>${esc(r.title)}</h3>
            <p class="card-desc">${esc(r.description||'')}</p>
            <p class="card-ings">${esc(ingList)}${more>0?` +${more} more`:''}</p>
            <div class="card-meta">
                <span>⏱️ ${r.total_time||'30 min'}</span>
                <span>🥘 ${(r.ingredients||[]).length} items</span>
            </div>
        </div>`;
    }).join("");
}


// ── RECIPE MODAL ────────────────────────────────────────────
function openRecipe(idx) {
    const r = recipes[idx];
    if (!r) return;
    const emoji = {breakfast:"🌅",lunch:"🥪",dinner:"🍽️",snack:"🍿",dessert:"🍰",side:"🥗"}[r.category]||"🍽️";

    document.getElementById("modal-body").innerHTML = `
        <div class="detail-head">
            <div class="detail-cat">${emoji} ${r.category||'dinner'}</div>
            <h2>${esc(r.title)}</h2>
            <p class="detail-desc">${esc(r.description||'')}</p>
        </div>

        <div class="detail-meta">
            <div class="meta-box"><div class="meta-lbl">Prep</div><div class="meta-val">${r.prep_time||'-'}</div></div>
            <div class="meta-box"><div class="meta-lbl">Cook</div><div class="meta-val">${r.cook_time||'-'}</div></div>
            <div class="meta-box"><div class="meta-lbl">Total</div><div class="meta-val">${r.total_time||'-'}</div></div>
            <div class="meta-box"><div class="meta-lbl">Servings</div><div class="meta-val">${r.servings||'2-4'}</div></div>
        </div>

        <div class="detail-section">
            <h3>Ingredients</h3>
            <ul class="ing-list">
                ${(r.ingredients||[]).map(i=>`<li><span class="ing-amt">${esc(i.amount||'')}</span> ${esc(i.item)}</li>`).join("")}
            </ul>
        </div>

        <div class="detail-section">
            <h3>Instructions</h3>
            <ol class="step-list">
                ${(r.instructions||[]).map(s=>`<li>${esc(s)}</li>`).join("")}
            </ol>
        </div>

        <div class="detail-section">
            <h3>Equipment</h3>
            <div class="equip-tags">
                ${(r.equipment||[]).map(e=>`<span class="equip-tag">🔧 ${esc(e)}</span>`).join("")}
            </div>
        </div>

        ${(r.substitutions_made||[]).length ? `
        <div class="detail-section">
            <div class="subs-box">
                <h4>Substitutions Made</h4>
                ${r.substitutions_made.map(s=>`<p>✅ ${esc(s)}</p>`).join("")}
            </div>
        </div>` : ''}

        ${r.tips ? `<div class="detail-section"><div class="tip-box">💡 ${esc(r.tips)}</div></div>` : ''}

        ${r.source_url ? `<div class="detail-source"><a href="${r.source_url}" target="_blank">🔗 Original Video</a></div>` : ''}
    `;

    document.getElementById("modal").classList.remove("hidden");
}

function closeModal() {
    document.getElementById("modal").classList.add("hidden");
}

async function deleteRecipe(idx) {
    if (!confirm("Delete this recipe?")) return;
    await fetch(`/api/recipes/${idx}`, {method: "DELETE"});
    loadRecipes();
}

async function refetchRecipes() {
    showScreen("processing");
    startPipeline();
}


// ── GROCERY LIST ────────────────────────────────────────────
function showGroceryPicker() {
    document.getElementById("grocery-content").innerHTML = `
        <p class="muted">Click <strong>Random Recipe</strong> to pick one, or click any recipe card first then come here.</p>`;
    document.getElementById("grocery-modal").classList.remove("hidden");
}

function closeGrocery() {
    document.getElementById("grocery-modal").classList.add("hidden");
}

async function pickRandomGrocery() {
    const el = document.getElementById("grocery-content");
    el.innerHTML = `<p class="muted">🎲 Picking a random recipe...</p>`;
    try {
        const res = await fetch("/api/grocery/pick", {method: "POST"});
        const data = await res.json();
        if (data.error) { el.innerHTML = `<p class="error-msg">${esc(data.error)}</p>`; return; }
        renderGroceryList(data);
    } catch (err) {
        el.innerHTML = `<p class="error-msg">Failed to pick recipe.</p>`;
    }
}

async function buildGroceryForRecipe(idx) {
    const el = document.getElementById("grocery-content");
    el.innerHTML = `<p class="muted">Building grocery list...</p>`;
    document.getElementById("grocery-modal").classList.remove("hidden");
    try {
        const res = await fetch(`/api/grocery/build/${idx}`, {method: "POST"});
        const data = await res.json();
        if (data.error) { el.innerHTML = `<p class="error-msg">${esc(data.error)}</p>`; return; }
        renderGroceryList(data);
    } catch (err) {
        el.innerHTML = `<p class="error-msg">Failed to build grocery list.</p>`;
    }
}

function renderGroceryList(data) {
    const el = document.getElementById("grocery-content");
    const r = data.recipe;
    const gl = data.grocery_list;
    if (!gl) { el.innerHTML = `<p class="error-msg">No grocery list returned.</p>`; return; }

    let html = `
        <div class="grocery-recipe-header">
            <h3>🍽️ ${esc(r.title)}</h3>
            <p class="muted">${esc(r.description || '')}</p>
        </div>
        <div class="grocery-aisles">`;

    for (const section of gl) {
        html += `
            <div class="aisle-section">
                <h4 class="aisle-name">${esc(section.aisle)}</h4>
                <ul class="aisle-items">`;
        for (const item of section.items) {
            html += `
                    <li>
                        <span class="item-name">${esc(item.amount)} ${esc(item.item)}</span>
                        ${item.tip ? `<span class="item-tip">📍 ${esc(item.tip)}</span>` : ''}
                    </li>`;
        }
        html += `</ul></div>`;
    }

    html += `</div>`;
    el.innerHTML = html;
}

async function sendGroceryEmail() {
    toast("📧 Sending grocery list email...");
    try {
        const res = await fetch("/api/grocery/send-now", {method: "POST"});
        const data = await res.json();
        if (data.error) { toast("⚠️ " + data.error); return; }
        toast("✅ Grocery list emailed!");
    } catch (err) {
        toast("⚠️ Failed to send email. Check settings.");
    }
}


// ── SETTINGS ────────────────────────────────────────────────
async function showSettings() {
    const res = await fetch("/api/settings");
    const d = await res.json();
    if (d.openai_api_key_set) document.getElementById("set-openai").placeholder = "••••••• (saved)";
    document.getElementById("set-whisper").value = d.whisper_model || "base";

    // Notification settings
    document.getElementById("set-notify-email").value = d.notification_email || "";
    document.getElementById("set-smtp-email").value = d.smtp_email || "";
    if (d.smtp_password_set) document.getElementById("set-smtp-pass").placeholder = "••••••• (saved)";
    document.getElementById("set-weekly-enabled").checked = d.weekly_email_enabled !== false;
    document.getElementById("set-autocheck").checked = d.auto_check_enabled !== false;
    document.getElementById("set-check-interval").value = String(d.check_interval_hours || 6);

    // Scheduler status
    loadSchedulerStatus();

    document.getElementById("settings-modal").classList.remove("hidden");
}

function closeSettings() {
    document.getElementById("settings-modal").classList.add("hidden");
}

async function saveSettings() {
    const key = document.getElementById("set-openai").value.trim();
    const model = document.getElementById("set-whisper").value;
    const body = {
        whisper_model: model,
        notification_email: document.getElementById("set-notify-email").value.trim(),
        smtp_email: document.getElementById("set-smtp-email").value.trim(),
        weekly_email_enabled: document.getElementById("set-weekly-enabled").checked,
        auto_check_enabled: document.getElementById("set-autocheck").checked,
        check_interval_hours: parseInt(document.getElementById("set-check-interval").value),
    };
    if (key) body.openai_api_key = key;
    const pass = document.getElementById("set-smtp-pass").value.trim();
    if (pass) body.smtp_password = pass;

    await fetch("/api/settings", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(body),
    });
    closeSettings();
    toast("Settings saved!");
}

async function testEmail() {
    toast("📧 Sending test email...");
    try {
        const res = await fetch("/api/notifications/test", {method: "POST"});
        const data = await res.json();
        if (data.error) { toast("⚠️ " + data.error); return; }
        toast("✅ Test email sent! Check your inbox.");
    } catch (err) {
        toast("⚠️ Failed to send test email.");
    }
}

async function loadSchedulerStatus() {
    try {
        const res = await fetch("/api/scheduler/status");
        const s = await res.json();
        const el = document.getElementById("scheduler-status");
        if (!el) return;
        el.innerHTML = `
            <div class="sched-info">
                <span class="sched-dot ${s.running ? 'green' : 'red'}"></span>
                Scheduler: ${s.running ? 'Running' : 'Stopped'}
            </div>
            ${s.last_check ? `<p class="sched-detail">Last check: ${new Date(s.last_check).toLocaleString()}</p>` : ''}
            ${s.next_email ? `<p class="sched-detail">Next email: ${s.next_email}</p>` : ''}
            ${s.recipes_found != null ? `<p class="sched-detail">New recipes found: ${s.recipes_found}</p>` : ''}`;
    } catch (err) { /* ignore */ }
}


// ── Utilities ───────────────────────────────────────────────
function esc(t) {
    if (!t) return "";
    const d = document.createElement("div");
    d.textContent = t;
    return d.innerHTML;
}

function toast(msg) {
    let c = document.querySelector(".toast-box");
    if (!c) { c = document.createElement("div"); c.className = "toast-box"; document.body.appendChild(c); }
    const t = document.createElement("div");
    t.className = "toast";
    t.textContent = msg;
    c.appendChild(t);
    setTimeout(() => { t.style.opacity = "0"; setTimeout(() => t.remove(), 300); }, 3000);
}

// Keyboard
document.addEventListener("keydown", e => { if (e.key === "Escape") { closeModal(); closeSettings(); closeGrocery(); } });
