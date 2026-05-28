let currentUser = null;

function logoutUser() {
  apiRequest("/api/v1/auth/logout", "POST")
    .catch(() => null)
    .finally(() => {
      currentUser = null;
      window.location.href = "/auth";
    });
}

function setupGlobalAuthUI(isAuthenticated) {
  const logoutBtn = document.getElementById("logoutBtn");
  const loginBtn = document.getElementById("navLoginBtn");
  const emailEl = document.getElementById("navUserEmail");
  const navDashItem = document.getElementById("navDashItem");
  const navAdminItem = document.getElementById("navAdminItem");

  if (isAuthenticated) {
    logoutBtn?.classList.remove("d-none");
    if (logoutBtn) logoutBtn.onclick = logoutUser;
    loginBtn?.classList.add("d-none");
    if (emailEl && currentUser?.email) {
      emailEl.textContent = currentUser.email;
      emailEl.classList.remove("d-none");
    }
    navDashItem?.classList.remove("d-none");
    if (currentUser?.role === "admin") {
      navAdminItem?.classList.remove("d-none");
    } else {
      navAdminItem?.classList.add("d-none");
    }
  } else {
    logoutBtn?.classList.add("d-none");
    if (logoutBtn) logoutBtn.onclick = null;
    loginBtn?.classList.remove("d-none");
    emailEl?.classList.add("d-none");
    navDashItem?.classList.add("d-none");
    navAdminItem?.classList.add("d-none");
  }

  // Highlight active nav link
  const currentPath = window.location.pathname;
  document.querySelectorAll(".navbar .nav-link").forEach((link) => {
    const href = link.getAttribute("href");
    link.classList.toggle("active", href === currentPath || (href !== "/" && currentPath.startsWith(href)));
  });
}

function showAlert(containerId, message, type = "success") {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.className = `alert alert-${type}`;
  el.textContent = message;
  el.classList.remove("d-none");
}

async function apiRequest(path, method = "GET", body = null) {
  const headers = { "Content-Type": "application/json" };

  const response = await fetch(path, {
    method,
    headers,
    credentials: "same-origin",
    body: body ? JSON.stringify(body) : null,
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = data.error?.message || data.detail || "Request failed";
    throw new Error(message);
  }
  return data;
}

async function fetchCurrentUser() {
  try {
    const user = await apiRequest("/api/v1/auth/me");
    currentUser = user.data || user;
    return currentUser;
  } catch (error) {
    currentUser = null;
    return null;
  }
}

async function initAuthPage() {
  const loginForm = document.getElementById("loginForm");
  const registerForm = document.getElementById("registerForm");

  loginForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(loginForm);
    try {
      await apiRequest(
        "/api/v1/auth/login",
        "POST",
        {
          email: formData.get("email"),
          password: formData.get("password"),
        },
      );
      const me = await fetchCurrentUser();
      showAlert("authAlert", "Login successful", "success");
      setTimeout(() => {
        window.location.href = me?.role === "admin" ? "/admin" : "/dashboard";
      }, 500);
    } catch (error) {
      showAlert("authAlert", error.message, "danger");
    }
  });

  registerForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(registerForm);
    try {
      await apiRequest(
        "/api/v1/auth/register",
        "POST",
        {
          email: formData.get("email"),
          password: formData.get("password"),
        },
      );
      showAlert("authAlert", "Account created. You can now login.", "success");
    } catch (error) {
      showAlert("authAlert", error.message, "danger");
    }
  });
}

async function initUserDashboard() {
  try {
    const me = currentUser || (await fetchCurrentUser());
    const txResult = await apiRequest("/api/v1/transactions?limit=100");
    const userTransactions = txResult.data || txResult;

    const txTable = document.getElementById("transactionsTable");

    txTable.innerHTML = "";
    userTransactions.forEach((tx) => {
      const dateStr = tx.createdAt ? formatTimestamp(tx.createdAt) : "—";
      txTable.insertAdjacentHTML(
        "beforeend",
        `<tr><td><code class="small">${tx.id.slice(-8)}</code></td><td>${tx.type}</td><td>$${Number(tx.amount || 0).toFixed(2)}</td><td><span class="badge ${tx.status === "completed" ? "bg-success" : "bg-warning text-dark"}">${tx.status}</span></td><td class="text-muted small">${dateStr}</td></tr>`,
      );
    });

    document.getElementById("roleValue").textContent = me?.role || "user";
    document.getElementById("balanceValue").textContent = `$${Number(me?.balance || 0).toFixed(2)}`;

    // Profile header
    const profileEmailEl = document.getElementById("profileEmail");
    const profileRoleBadge = document.getElementById("profileRoleBadge");
    if (profileEmailEl) profileEmailEl.textContent = me?.email || "";
    if (profileRoleBadge) {
      profileRoleBadge.textContent = me?.role || "user";
      profileRoleBadge.className = `badge small mt-1 ${me?.role === "admin" ? "bg-danger" : "bg-secondary"}`;
    }

    // §4.3 Change password
    document.getElementById("changePasswordForm")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const msgEl = document.getElementById("passwordMsg");
      const currentPassword = document.getElementById("currentPassword").value;
      const newPassword = document.getElementById("newPassword").value;
      try {
        await apiRequest("/api/v1/users/me/password", "PATCH", { currentPassword, newPassword });
        event.target.reset();
        msgEl.textContent = "Password updated successfully.";
        msgEl.className = "col-12 small mt-1 text-success";
        msgEl.classList.remove("d-none");
      } catch (error) {
        msgEl.textContent = error.message;
        msgEl.className = "col-12 small mt-1 text-danger";
        msgEl.classList.remove("d-none");
      }
    });

    // §4.3 Delete own account
    document.getElementById("deleteAccountBtn")?.addEventListener("click", async () => {
      if (!confirm("Are you sure you want to delete your account? This cannot be undone.")) return;
      try {
        await apiRequest("/api/v1/users/me", "DELETE");
        window.location.href = "/";
      } catch (error) {
        showAlert("dashboardAlert", error.message, "danger");
      }
    });

    // Linked accounts — populate fields then wire save
    const discordInput = document.getElementById("discordIdInput");
    const fivemInput = document.getElementById("fivemIdInput");
    const discordBadge = document.getElementById("discordStatusBadge");
    const fivemBadge = document.getElementById("fivemStatusBadge");

    function setLinkedBadge(badge, value) {
      if (!badge) return;
      if (value) {
        badge.textContent = "✓ Linked";
        badge.style.cssText = "background:#1a3a1a;color:#71d08d;border:1px solid rgba(113,208,141,0.35);";
      } else {
        badge.textContent = "Not linked";
        badge.style.cssText = "background:rgba(255,255,255,0.06);color:#888;border:1px solid rgba(255,255,255,0.1);";
      }
    }

    if (discordInput) discordInput.value = me?.discordId || "";
    if (fivemInput) fivemInput.value = me?.fivemId || "";
    setLinkedBadge(discordBadge, me?.discordId);
    setLinkedBadge(fivemBadge, me?.fivemId);

    document.getElementById("linkedAccountsForm")?.addEventListener("submit", async (event) => {
      event.preventDefault();
      const msgEl = document.getElementById("linkedAccountsMsg");
      try {
        const result = await apiRequest("/api/v1/users/me/linked-accounts", "PATCH", {
          discordId: discordInput?.value.trim() || null,
          fivemId: fivemInput?.value.trim() || null,
        });
        const data = result.data || result;
        setLinkedBadge(discordBadge, data.discordId);
        setLinkedBadge(fivemBadge, data.fivemId);
        msgEl.textContent = "Connections saved.";
        msgEl.className = "small text-success";
        msgEl.classList.remove("d-none");
      } catch (error) {
        msgEl.textContent = error.message;
        msgEl.className = "small text-danger";
        msgEl.classList.remove("d-none");
      }
    });

  } catch (error) {
    showAlert("dashboardAlert", error.message, "danger");
  }
}

async function buyWithBalance(itemId) {
  try {
    await apiRequest("/api/v1/store/buy", "POST", { itemId });
    showAlert("dashboardAlert", "Purchase successful! Your balance has been updated.", "success");
    // Reload to reflect new balance and transaction
    const [me, txResult, itemsResult] = await Promise.all([
      fetchCurrentUser(),
      apiRequest("/api/v1/transactions?limit=100"),
      apiRequest("/api/v1/store/items?limit=100"),
    ]);
    currentUser = me;
    await initUserDashboard();
  } catch (error) {
    showAlert("dashboardAlert", error.message, "danger");
  }
}

async function buyItem(itemId) {
  try {
    const data = await apiRequest("/api/v1/payments/create-checkout-session", "POST", { itemId });
    window.location.href = data.url;
  } catch (error) {
    showAlert("dashboardAlert", error.message, "danger");
  }
}

function switchPanel(name) {
  document.querySelectorAll("[data-admin-panel]").forEach((panel) => {
    panel.classList.toggle("d-none", panel.dataset.adminPanel !== name);
  });
  document.querySelectorAll("[data-panel]").forEach((link) => {
    link.classList.toggle("active", link.dataset.panel === name);
  });

  // Start/stop fivem-players auto-refresh
  if (_fivemPlayersInterval) {
    clearInterval(_fivemPlayersInterval);
    _fivemPlayersInterval = null;
  }
  if (name === "fivem-players") {
    loadFivemPlayers();
    _fivemPlayersInterval = setInterval(loadFivemPlayers, 10000);
  }
}

async function simulateFivemRewards() {
  try {
    const result = await apiRequest("/api/v1/admin/simulate-fivem-rewards", "POST");
    const data = result.data || result;
    const message = data.message || `FiveM pickup simulated — ${data.confirmed} transaction(s) confirmed.`;
    showAlert("adminAlert", message, "success");
    await Promise.all([loadAdminOverview(), loadAdminTransactions()]);
  } catch (error) {
    showAlert("adminAlert", error.message, "danger");
  }
}

async function simulateFivemActions() {
  try {
    const result = await apiRequest("/api/v1/admin/simulate-fivem-actions", "POST");
    const data = result.data || result;
    const message = data.message || `FiveM action pickup simulated — ${data.confirmed} action(s) confirmed.`;
    showAlert("adminAlert", message, "success");
    await loadAdminOverview();
  } catch (error) {
    showAlert("adminAlert", error.message, "danger");
  }
}

async function simulateDiscordPickup() {
  try {
    const result = await apiRequest("/api/v1/admin/simulate-discord-pickup", "POST");
    const data = result.data || result;
    const suffix = data.webhookSent ? " Discord message sent." : " Discord webhook not configured.";
    const message = (data.message || `Discord pickup simulated — ${data.confirmed} action(s) confirmed.`) + suffix;
    showAlert("adminAlert", message, "success");
    await loadAdminOverview();
  } catch (error) {
    showAlert("adminAlert", error.message, "danger");
  }
}

async function loadFivemPlayers() {
  const tbody = document.getElementById("fivemPlayersTbody");
  const countBadge = document.getElementById("fivemPlayerCount");
  const updatedEl = document.getElementById("fivemPlayersUpdatedAt");
  if (!tbody) return;
  try {
    const result = await apiRequest("/api/v1/service/fivem/players");
    const data = result.data || result;
    const players = Array.isArray(data.players) ? data.players : [];
    if (countBadge) countBadge.textContent = `${players.length} online`;
    if (updatedEl && data.updatedAt) {
      updatedEl.textContent = `Last update: ${new Date(data.updatedAt).toLocaleTimeString()}`;
    }
    if (!players.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="text-center text-light-subtle py-4">No players online</td></tr>';
      return;
    }
    tbody.innerHTML = players.map((p) => {
      const roles = Array.isArray(p.roles) ? p.roles.join(", ") : (p.roles || "—");
      const status = p.banned ? '<span class="badge bg-danger">Banned</span>' : '<span class="badge bg-success">Online</span>';
      return `<tr>
        <td><code>${p.id ?? "—"}</code></td>
        <td>${p.name ?? "—"}</td>
        <td>$${(p.money ?? 0).toLocaleString()}</td>
        <td>${roles}</td>
        <td>${status}</td>
      </tr>`;
    }).join("");
  } catch (error) {
    tbody.innerHTML = `<tr><td colspan="5" class="text-center text-danger py-4">${error.message}</td></tr>`;
  }
}

let _fivemPlayersInterval = null;

async function loadAdminHistory() {
  try {
    const actionsResult = await apiRequest("/api/v1/admin-actions/history?limit=100");
    const actions = actionsResult.data || actionsResult;
    const table = document.getElementById("adminHistoryTable");
    if (!table) return;
    table.innerHTML = "";
    if (!actions.length) {
      table.innerHTML = '<tr><td colspan="4" class="text-light-subtle">No actions recorded yet.</td></tr>';
      return;
    }
    actions.forEach((action) => {
      table.insertAdjacentHTML(
        "beforeend",
        `<tr>
          <td>${action.type}</td>
          <td>${action.playerId}</td>
          <td><span class="badge ${action.status === 'completed' ? 'bg-success' : 'bg-warning text-dark'}">${action.status}</span></td>
          <td>${formatTimestamp(action.createdAt)}</td>
        </tr>`,
      );
    });
  } catch {
    /* non-critical */
  }
}

async function initAdminPage() {
  const cards = document.querySelectorAll(".glass-card, .metric-card");
  cards.forEach((card, idx) => {
    card.classList.add("card-pop");
    card.style.animationDelay = `${idx * 40}ms`;
  });

  // Panel navigation
  document.querySelectorAll("[data-panel]").forEach((link) => {
    link.addEventListener("click", (e) => {
      e.preventDefault();
      switchPanel(link.dataset.panel);
    });
  });

  // Default panel
  switchPanel("fivem-rewards");

  try {
    await Promise.all([loadUsers(), loadAdminTransactions(), loadAdminOverview(), loadAdminHistory(), loadAdminStore(), loadAdminTopupPackages()]);
  } catch (error) {
    showAlert("adminAlert", error.message, "danger");
  }

  document.getElementById("refreshOperationsBtn")?.addEventListener("click", async () => {
    try {
      await Promise.all([loadAdminOverview(), loadAdminTransactions(), loadAdminHistory()]);
      showAlert("adminAlert", "Operations data refreshed", "success");
    } catch (error) {
      showAlert("adminAlert", error.message, "danger");
    }
  });

  document.getElementById("simulateFivemRewardsBtn")?.addEventListener("click", simulateFivemRewards);
  document.getElementById("simulateFivemActionsBtn")?.addEventListener("click", simulateFivemActions);
  document.getElementById("simulateDiscordPickupBtn")?.addEventListener("click", simulateDiscordPickup);

  // User search
  document.getElementById("userSearchBtn")?.addEventListener("click", async () => {
    const q = document.getElementById("userSearchInput")?.value.trim() || "";
    await loadUsers(q);
  });
  document.getElementById("userSearchInput")?.addEventListener("keydown", async (e) => {
    if (e.key === "Enter") {
      const q = e.target.value.trim();
      await loadUsers(q);
    }
  });

  // Save edited store item
  document.getElementById("saveStoreItemBtn")?.addEventListener("click", async () => {
    const itemId = document.getElementById("editItemId").value;
    const name = document.getElementById("editItemName").value.trim();
    const price = Number(document.getElementById("editItemPrice").value);
    const rewardDataRaw = document.getElementById("editItemRewardData").value.trim();
    let rewardData;
    try {
      rewardData = JSON.parse(rewardDataRaw);
    } catch {
      showAlert("adminAlert", "Reward data is not valid JSON", "danger");
      return;
    }
    try {
      await apiRequest(`/api/v1/store/items/${itemId}`, "PATCH", { name, price, rewardData });
      showAlert("adminAlert", "Store item updated", "success");
      bootstrap.Modal.getInstance(document.getElementById("editStoreItemModal"))?.hide();
      await loadAdminStore();
    } catch (error) {
      showAlert("adminAlert", error.message, "danger");
    }
  });

  document.getElementById("storeItemForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    const formData = new FormData(form);
    let rewardData;
    try {
      rewardData = JSON.parse(formData.get("rewardData"));
    } catch {
      showAlert("adminAlert", 'Reward Data must be valid JSON — e.g. {"type": "money", "amount": 1000}', "danger");
      return;
    }
    try {
      await apiRequest("/api/v1/store/items", "POST", {
        name: formData.get("name"),
        price: Number(formData.get("price")),
        rewardData,
      });
      showAlert("adminAlert", "Store item created", "success");
      form.reset();
      await loadAdminStore();
    } catch (error) {
      showAlert("adminAlert", error.message, "danger");
    }
  });

  document.getElementById("adminActionForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    const formData = new FormData(form);
    try {
      await apiRequest("/api/v1/admin-actions", "POST", {
        type: formData.get("type"),
        playerId: formData.get("playerId"),
        data: JSON.parse(formData.get("data")),
      });
      showAlert("adminAlert", "Admin action queued", "success");
      form.reset();
    } catch (error) {
      showAlert("adminAlert", error.message, "danger");
    }
  });

  document.getElementById("topupPackageForm")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = document.getElementById("pkgName").value.trim();
    const amount = Number(document.getElementById("pkgAmount").value);
    const description = document.getElementById("pkgDescription").value.trim();
    const msgEl = document.getElementById("pkgFormMsg");
    try {
      await apiRequest("/api/v1/admin/topup-packages", "POST", { name, amount, description });
      event.target.reset();
      msgEl.textContent = "Package created.";
      msgEl.className = "col-12 small mt-1 text-success";
      msgEl.classList.remove("d-none");
      await loadAdminTopupPackages();
    } catch (error) {
      msgEl.textContent = error.message;
      msgEl.className = "col-12 small mt-1 text-danger";
      msgEl.classList.remove("d-none");
    }
  });

  // Creator tab switching
  document.querySelectorAll("[data-creator-tab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("[data-creator-tab]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      document.querySelectorAll("[data-creator-panel]").forEach((panel) => {
        panel.classList.toggle("d-none", panel.dataset.creatorPanel !== btn.dataset.creatorTab);
      });
    });
  });

  // Tabbed action form submissions
  document.getElementById("webActionForm")?.addEventListener("submit", (e) => submitCreatorAction(e, "web"));
  document.getElementById("fivemActionForm")?.addEventListener("submit", (e) => submitCreatorAction(e, "fivem"));
  document.getElementById("discordActionForm")?.addEventListener("submit", (e) => submitCreatorAction(e, "discord"));
}

async function loadAdminTopupPackages() {
  const result = await apiRequest("/api/v1/topup-packages");
  const packages = result.data || result;
  const table = document.getElementById("topupPackagesTable");
  if (!table) return;
  table.innerHTML = "";
  if (!packages.length) {
    table.innerHTML = '<tr><td colspan="4" class="text-light-subtle">No packages yet.</td></tr>';
    return;
  }
  packages.forEach((pkg) => {
    table.insertAdjacentHTML(
      "beforeend",
      `<tr>
        <td>${pkg.name}</td>
        <td>$${Number(pkg.amount).toFixed(2)}</td>
        <td>${pkg.description || "—"}</td>
        <td><button class="btn btn-outline-danger btn-sm" onclick="deleteTopupPackage('${pkg.id}', '${pkg.name}')"><i class="bi bi-trash"></i></button></td>
      </tr>`,
    );
  });
}

// ===================== ACTION CREATOR HELPERS =====================

function fillWebAction(type, dataObj) {
  document.getElementById("webActionType").value = type;
  document.getElementById("webActionData").value = JSON.stringify(dataObj, null, 2);
  document.getElementById("webActionPlayerId").focus();
}

function fillFivemAction(type, dataObj) {
  document.getElementById("fivemActionType").value = type;
  document.getElementById("fivemActionData").value = JSON.stringify(dataObj, null, 2);
  document.getElementById("fivemActionPlayerId").focus();
}

function fillDiscordAction(type, dataObj) {
  document.getElementById("discordActionType").value = type;
  document.getElementById("discordActionData").value = JSON.stringify(dataObj, null, 2);
  document.getElementById("discordActionPlayerId").focus();
}

async function submitCreatorAction(event, source) {
  event.preventDefault();
  const prefix = source === "web" ? "web" : source === "fivem" ? "fivem" : "discord";
  const playerIdEl = document.getElementById(`${prefix}ActionPlayerId`);
  const typeEl = document.getElementById(`${prefix}ActionType`);
  const dataEl = document.getElementById(`${prefix}ActionData`);
  const customEl = document.getElementById(`${prefix}ActionCustom`);

  const playerId = playerIdEl?.value.trim();
  const type = typeEl?.value.trim();
  const customCommand = customEl?.value.trim() || undefined;
  const rawData = dataEl?.value.trim();

  let data = {};
  if (rawData) {
    try { data = JSON.parse(rawData); }
    catch { showAlert("adminAlert", "Data field is not valid JSON", "danger"); return; }
  }
  if (!playerId || !type) {
    showAlert("adminAlert", "Player ID and Action Type are required", "warning");
    return;
  }
  try {
    const body = { type, playerId, data };
    if (customCommand) body.customCommand = customCommand;
    await apiRequest("/api/v1/admin-actions", "POST", body);
    showAlert("adminAlert", `${source.charAt(0).toUpperCase() + source.slice(1)} action queued`, "success");
    playerIdEl.value = "";
    typeEl.value = "";
    if (dataEl) dataEl.value = "";
    if (customEl) customEl.value = "";
  } catch (error) {
    showAlert("adminAlert", error.message, "danger");
  }
}

async function deleteTopupPackage(pkgId, name) {
  if (!confirm(`Delete package "${name}"?`)) return;
  try {
    await apiRequest(`/api/v1/admin/topup-packages/${pkgId}`, "DELETE");
    showAlert("adminAlert", `Package "${name}" deleted`, "success");
    await loadAdminTopupPackages();
  } catch (error) {
    showAlert("adminAlert", error.message, "danger");
  }
}

async function loadUsers(search = "") {
  const limit = document.getElementById("usersLimitSelect")?.value || "25";
  const url = search
    ? `/api/v1/users?limit=${limit}&search=${encodeURIComponent(search)}`
    : `/api/v1/users?limit=${limit}`;
  const usersResult = await apiRequest(url);
  const users = usersResult.data || usersResult;
  const table = document.getElementById("usersTable");
  table.innerHTML = "";

  const totalUsersEl = document.getElementById("statUsers");
  if (totalUsersEl) {
    totalUsersEl.textContent = String(usersResult.meta?.total ?? users.length);
  }

  const roleBadge = (role) => {
    const cls = role === "admin" ? "bg-danger" : "bg-secondary";
    return `<span class="badge ${cls}">${role}</span>`;
  };
  const statusBadge = (banned) =>
    banned
      ? '<span class="badge bg-danger">Banned</span>'
      : '<span class="badge bg-success">Active</span>';
  const linkBadge = (val) =>
    val ? '<span class="badge bg-success"><i class="bi bi-check2"></i> Linked</span>'
        : '<span class="badge bg-dark text-light-subtle border border-secondary">—</span>';
  const fmtDate = (d) => {
    if (!d) return "—";
    return new Date(d).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  };

  users.forEach((user) => {
    const banned = user.is_banned || user.banned || false;
    const banLabel = banned ? "Unban" : "Ban";
    const banClass = banned ? "btn-outline-success" : "btn-outline-danger";
    table.insertAdjacentHTML(
      "beforeend",
      `<tr>
        <td><input type="checkbox" class="form-check-input user-select-cb" data-id="${user.id}" data-email="${user.email}"></td>
        <td><span class="fw-semibold">${user.email}</span></td>
        <td>${roleBadge(user.role)}</td>
        <td>$${Number(user.balance || 0).toFixed(2)}</td>
        <td>${linkBadge(user.discord_id)}</td>
        <td>${linkBadge(user.fivem_id || user.fivem_license)}</td>
        <td>${statusBadge(banned)}</td>
        <td class="text-light-subtle small">${fmtDate(user.createdAt || user.created_at)}</td>
        <td class="text-end">
          <div class="d-flex gap-1 justify-content-end flex-wrap">
            <button class="btn btn-outline-secondary btn-sm" title="Adjust balance"
              onclick="openAdjustBalance('${user.id}','${user.email}')">
              <i class="bi bi-cash"></i>
            </button>
            <button class="btn btn-outline-info btn-sm" title="Change role"
              onclick="openChangeRole('${user.id}','${user.email}','${user.role}')">
              <i class="bi bi-shield"></i>
            </button>
            <button class="btn ${banClass} btn-sm" title="${banLabel}"
              onclick="${banned ? `unbanUser('${user.id}','${user.email}')` : `banUser('${user.id}','${user.email}')`}">
              <i class="bi bi-${banned ? 'check-circle' : 'ban'}"></i>
            </button>
            <button class="btn btn-outline-danger btn-sm" title="Delete"
              onclick="deleteUser('${user.id}','${user.email}')">
              <i class="bi bi-trash"></i>
            </button>
          </div>
        </td>
      </tr>`,
    );
  });

  // Wire up select-all checkbox
  const selectAll = document.getElementById("userSelectAll");
  if (selectAll) {
    selectAll.checked = false;
    selectAll.onchange = () => {
      document.querySelectorAll(".user-select-cb").forEach((cb) => {
        cb.checked = selectAll.checked;
      });
      updateBulkBar();
    };
  }
  document.querySelectorAll(".user-select-cb").forEach((cb) => {
    cb.onchange = updateBulkBar;
  });
}

function updateBulkBar() {
  const selected = document.querySelectorAll(".user-select-cb:checked");
  const bar = document.getElementById("usersBulkBar");
  const countEl = document.getElementById("bulkSelCount");
  if (!bar) return;
  if (selected.length > 0) {
    bar.classList.remove("d-none");
    if (countEl) countEl.textContent = `${selected.length} selected`;
  } else {
    bar.classList.add("d-none");
  }
}

function openAdjustBalance(userId, email) {
  document.getElementById("adjustBalanceUserId").value = userId;
  document.getElementById("adjustBalanceEmail").textContent = email;
  document.getElementById("adjustBalanceAmount").value = "";
  new bootstrap.Modal(document.getElementById("adjustBalanceModal")).show();
}

async function applyBalanceAdjust() {
  const userId = document.getElementById("adjustBalanceUserId").value;
  const amount = Number(document.getElementById("adjustBalanceAmount").value);
  if (!amount) { showAlert("adminAlert", "Enter a non-zero amount", "warning"); return; }
  try {
    await apiRequest(`/api/v1/users/${userId}/balance`, "PATCH", { amount });
    showAlert("adminAlert", "Balance updated", "success");
    bootstrap.Modal.getInstance(document.getElementById("adjustBalanceModal"))?.hide();
    await loadUsers();
  } catch (error) {
    showAlert("adminAlert", error.message, "danger");
  }
}

function openChangeRole(userId, email, currentRole) {
  document.getElementById("changeRoleUserId").value = userId;
  document.getElementById("changeRoleEmail").textContent = email;
  document.getElementById("changeRoleSelect").value = currentRole;
  new bootstrap.Modal(document.getElementById("changeRoleModal")).show();
}

async function applyRoleChange() {
  const userId = document.getElementById("changeRoleUserId").value;
  const role = document.getElementById("changeRoleSelect").value;
  try {
    await apiRequest(`/api/v1/users/${userId}/role`, "PATCH", { role });
    showAlert("adminAlert", `Role set to "${role}"`, "success");
    bootstrap.Modal.getInstance(document.getElementById("changeRoleModal"))?.hide();
    await loadUsers();
  } catch (error) {
    showAlert("adminAlert", error.message, "danger");
  }
}

async function banUser(userId, email) {
  if (!confirm(`Ban user "${email}"?`)) return;
  try {
    await apiRequest(`/api/v1/users/${userId}/ban`, "POST", { reason: "Admin action" });
    showAlert("adminAlert", `User "${email}" banned`, "success");
    await loadUsers();
  } catch (error) {
    showAlert("adminAlert", error.message, "danger");
  }
}

async function unbanUser(userId, email) {
  if (!confirm(`Unban user "${email}"?`)) return;
  try {
    await apiRequest(`/api/v1/users/${userId}/unban`, "POST");
    showAlert("adminAlert", `User "${email}" unbanned`, "success");
    await loadUsers();
  } catch (error) {
    showAlert("adminAlert", error.message, "danger");
  }
}

async function bulkBanUsers() {
  const selected = [...document.querySelectorAll(".user-select-cb:checked")];
  if (!selected.length) return;
  if (!confirm(`Ban ${selected.length} selected user(s)?`)) return;
  let ok = 0, fail = 0;
  for (const cb of selected) {
    try {
      await apiRequest(`/api/v1/users/${cb.dataset.id}/ban`, "POST", { reason: "Bulk ban by admin" });
      ok++;
    } catch { fail++; }
  }
  showAlert("adminAlert", `Banned ${ok} user(s)${fail ? `, ${fail} failed` : ""}`, fail ? "warning" : "success");
  await loadUsers();
}

async function bulkDeleteUsers() {
  const selected = [...document.querySelectorAll(".user-select-cb:checked")];
  if (!selected.length) return;
  if (!confirm(`Permanently delete ${selected.length} selected user(s)?`)) return;
  let ok = 0, fail = 0;
  for (const cb of selected) {
    try {
      await apiRequest(`/api/v1/users/${cb.dataset.id}`, "DELETE");
      ok++;
    } catch { fail++; }
  }
  showAlert("adminAlert", `Deleted ${ok} user(s)${fail ? `, ${fail} failed` : ""}`, fail ? "warning" : "success");
  await loadUsers();
}

async function loadAdminStore() {
  const result = await apiRequest("/api/v1/store/items?limit=100");
  const items = result.data || result;
  const table = document.getElementById("adminStoreTable");
  if (!table) return;
  table.innerHTML = "";
  items.forEach((item) => {
    table.insertAdjacentHTML(
      "beforeend",
      `<tr>
        <td>${item.name}</td>
        <td>$${Number(item.price).toFixed(2)}</td>
        <td><small>${JSON.stringify(item.rewardData || {})}</small></td>
        <td><button class="btn btn-outline-secondary btn-sm" onclick="openEditStoreItem('${item.id}', ${JSON.stringify(item.name).replace(/"/g, '&quot;')}, ${item.price}, ${JSON.stringify(JSON.stringify(item.rewardData || {})).replace(/"/g, '&quot;')})">Edit</button></td>
        <td><button class="btn btn-outline-danger btn-sm" onclick="deleteStoreItem('${item.id}', '${item.name}')"><i class="bi bi-trash"></i></button></td>
      </tr>`,
    );
  });
}

function openEditStoreItem(itemId, name, price, rewardDataJson) {
  document.getElementById("editItemId").value = itemId;
  document.getElementById("editItemName").value = name;
  document.getElementById("editItemPrice").value = price;
  document.getElementById("editItemRewardData").value = rewardDataJson;
  const modal = new bootstrap.Modal(document.getElementById("editStoreItemModal"));
  modal.show();
}

async function deleteStoreItem(itemId, name) {
  if (!confirm(`Delete store item "${name}"?`)) return;
  try {
    await apiRequest(`/api/v1/store/items/${itemId}`, "DELETE");
    showAlert("adminAlert", `Store item "${name}" deleted`, "success");
    await loadAdminStore();
  } catch (error) {
    showAlert("adminAlert", error.message, "danger");
  }
}

async function loadAdminTransactions() {
  const limit = document.getElementById("txLimitSelect")?.value || "25";
  const status = document.getElementById("txStatusFilter")?.value || "";
  const type = document.getElementById("txTypeFilter")?.value || "";
  let url = `/api/v1/transactions?limit=${limit}`;
  if (status) url += `&status=${encodeURIComponent(status)}`;
  if (type) url += `&type=${encodeURIComponent(type)}`;

  const txResult = await apiRequest(url);
  const transactions = txResult.data || txResult;
  const table = document.getElementById("adminTransactionsTable");
  table.innerHTML = "";

  const pendingCount = transactions.filter((tx) => tx.status === "pending").length;
  const completedCount = transactions.filter((tx) => tx.status === "completed").length;

  const pendingEl = document.getElementById("statPendingTx");
  const completedEl = document.getElementById("statCompletedTx");
  if (pendingEl) pendingEl.textContent = String(pendingCount);
  if (completedEl) completedEl.textContent = String(completedCount);

  const statusBadge = (s) => {
    const map = { pending: "warning", completed: "success", failed: "danger", refunded: "secondary" };
    return `<span class="badge bg-${map[s] || "secondary"}">${s}</span>`;
  };
  const typeBadge = (t) => {
    const map = { topup: "info", purchase: "primary", credit: "success", debit: "danger" };
    return `<span class="badge bg-${map[t] || "secondary"} bg-opacity-75 text-light">${t}</span>`;
  };
  const fmtDate = (d) => {
    if (!d) return "—";
    return new Date(d).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  };
  const shortId = (id) => {
    if (!id || id.length <= 8) return id || "—";
    return `<span title="${id}" class="font-monospace small">${id.slice(0, 8)}…</span>`;
  };

  if (!transactions.length) {
    table.innerHTML = '<tr><td colspan="7" class="text-light-subtle text-center py-3">No transactions found.</td></tr>';
    return;
  }

  transactions.forEach((tx) => {
    const isRefundable = tx.status === "completed" && tx.type === "purchase";
    table.insertAdjacentHTML(
      "beforeend",
      `<tr>
        <td>${shortId(tx.id)}</td>
        <td class="small">${tx.userEmail || tx.userId || "—"}</td>
        <td>${typeBadge(tx.type || "—")}</td>
        <td class="fw-semibold">$${Number(tx.amount || 0).toFixed(2)}</td>
        <td>${statusBadge(tx.status)}</td>
        <td class="text-light-subtle small">${fmtDate(tx.createdAt || tx.created_at)}</td>
        <td class="text-end">
          ${isRefundable ? `<button class="btn btn-outline-warning btn-sm" onclick="refundTransaction('${tx.id}')"><i class="bi bi-arrow-counterclockwise me-1"></i>Refund</button>` : "—"}
        </td>
      </tr>`,
    );
  });
}

async function refundTransaction(txId) {
  if (!confirm("Refund this transaction?")) return;
  try {
    await apiRequest(`/api/v1/transactions/${txId}/refund`, "POST");
    showAlert("adminAlert", "Transaction refunded", "success");
    await loadAdminTransactions();
  } catch (error) {
    showAlert("adminAlert", error.message, "danger");
  }
}

async function loadAdminOverview() {
  const overview = await apiRequest("/api/v1/dashboard/overview");
  const overviewData = overview.data || overview;
  const stats = overviewData.stats || {};

  setText("statUsers", stats.users ?? 0);
  setText("statPendingTx", stats.pendingTransactions ?? 0);
  setText("statCompletedTx", stats.completedTransactions ?? 0);
  setText("statPendingActions", stats.pendingAdminActions ?? 0);
  setText("statStoreItems", stats.storeItems ?? 0);
  setText("statSyncTime", formatTimestamp(overviewData.generatedAt));

  setText("opsPendingTransactions", stats.pendingTransactions ?? 0);
  setText("opsPendingAdminActions", stats.pendingAdminActions ?? 0);
  setText("opsCompletedActions", stats.completedAdminActions ?? 0);
  setText("opsCompletedTransactions", stats.completedTransactions ?? 0);
  setText("operationsStatusText", buildOperationsStatusText(stats));

  renderPendingTransactions(overviewData.pendingTransactions || []);
  renderPendingAdminActions(overviewData.pendingAdminActions || []);
  renderEndpointCards(overviewData.serviceEndpoints || {});
}

function setText(id, value) {
  const element = document.getElementById(id);
  if (element) {
    element.textContent = String(value);
  }
}

function formatTimestamp(value) {
  if (!value) return "Unknown";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function buildOperationsStatusText(stats) {
  const pendingTransactions = Number(stats.pendingTransactions || 0);
  const pendingAdminActions = Number(stats.pendingAdminActions || 0);
  if (!pendingTransactions && !pendingAdminActions) {
    return "No pending service work. Create a purchase or admin action to test FiveM and Discord polling.";
  }

  return `${pendingTransactions} transaction(s) and ${pendingAdminActions} admin action(s) waiting for service pickup.`;
}

function renderPendingTransactions(items) {
  const table = document.getElementById("pendingTransactionsTable");
  if (!table) return;

  table.innerHTML = "";
  if (!items.length) {
    table.innerHTML = '<tr><td colspan="4" class="text-light-subtle">No pending reward transactions.</td></tr>';
    return;
  }

  items.forEach((item) => {
    const itemId = item.itemId || "-";
    table.insertAdjacentHTML(
      "beforeend",
      `<tr><td>${item.userId || "-"}</td><td>${item.amount}</td><td><code class="small">${itemId}</code></td><td>${item.status}</td></tr>`,
    );
  });
}

function renderPendingAdminActions(items) {
  // Populates both the FiveM admin actions panel and the Discord queue panel
  ["pendingAdminActionsTable", "discordQueueTable"].forEach((tableId) => {
    const table = document.getElementById(tableId);
    if (!table) return;
    table.innerHTML = "";
    if (!items.length) {
      table.innerHTML = '<tr><td colspan="4" class="text-light-subtle">No pending admin actions.</td></tr>';
      return;
    }
    items.forEach((item) => {
      const dataPreview = item.data ? JSON.stringify(item.data).slice(0, 40) : "-";
      table.insertAdjacentHTML(
        "beforeend",
        `<tr><td>${item.type}</td><td>${item.playerId}</td><td><code class="small">${dataPreview}</code></td><td>${item.status}</td></tr>`,
      );
    });
  });
}

function renderEndpointCards(endpoints) {
  const container = document.getElementById("endpointCards");
  if (!container) return;

  const entries = Object.entries(endpoints);
  container.innerHTML = "";
  entries.forEach(([key, path]) => {
    container.insertAdjacentHTML(
      "beforeend",
      `<div class="endpoint-card"><h6>${humanizeKey(key)}</h6><code>http://127.0.0.1:8000${path}</code></div>`,
    );
  });
}

function humanizeKey(key) {
  return key.replace(/([A-Z])/g, " $1").replace(/^./, (char) => char.toUpperCase());
}

(async function bootstrapPage() {
  const me = await fetchCurrentUser();
  setupGlobalAuthUI(Boolean(me));

  const page = document.body.dataset.page;

  if (page === "index") {
    initHomePage();
  }

  if (page === "auth") {
    if (me) {
      window.location.href = me.role === "admin" ? "/admin" : "/dashboard";
      return;
    }
    initAuthPage();
  }

  if (page === "dashboard") {
    if (!me) {
      window.location.href = "/auth";
      return;
    }
    initUserDashboard();
  }

  if (page === "admin") {
    if (!me) {
      window.location.href = "/auth";
      return;
    }
    if (me.role !== "admin") {
      window.location.href = "/dashboard";
      return;
    }
    initAdminPage();
  }

  if (page === "store") {
    initStorePage(me);
  }
})();

async function initStorePage(me) {
  // Show/hide balance bar and login notice
  const balanceBar = document.getElementById("storeBalanceBar");
  const loginNotice = document.getElementById("storeLoginNotice");
  const topupSection = document.getElementById("topupSection");
  const storeBalanceEl = document.getElementById("storeBalance");

  if (me) {
    balanceBar?.classList.remove("d-none");
    loginNotice?.classList.add("d-none");
    topupSection?.classList.remove("d-none");
    if (storeBalanceEl) storeBalanceEl.textContent = `$${Number(me.balance || 0).toFixed(2)}`;
  } else {
    balanceBar?.classList.add("d-none");
    loginNotice?.classList.remove("d-none");
    topupSection?.classList.remove("d-none"); // still show packages even to guests
  }

  // Load topup packages
  try {
    const pkgResult = await apiRequest("/api/v1/topup-packages");
    const packages = pkgResult.data || pkgResult;
    const grid = document.getElementById("topupPackageGrid");
    const noMsg = document.getElementById("noPackagesMsg");
    if (grid) {
      if (packages.length) {
        grid.innerHTML = "";
        packages.forEach((pkg) => {
          grid.insertAdjacentHTML(
            "beforeend",
            `<div class="col-sm-6 col-lg-3">
              <div class="topup-package-card h-100 p-3 text-center">
                <div class="pkg-amount fw-bold fs-4 text-silver">$${Number(pkg.amount).toFixed(2)}</div>
                <div class="pkg-name fw-semibold mt-1">${pkg.name}</div>
                <div class="pkg-desc text-muted small mt-1">${pkg.description || ""}</div>
                <button class="btn btn-silver btn-sm mt-3 w-100" ${me ? "" : "disabled title='Login to purchase'"}
                  onclick="topupWithPackage(${pkg.amount})">
                  <i class="bi bi-credit-card me-1"></i>Buy
                </button>
              </div>
            </div>`,
          );
        });
        noMsg?.classList.add("d-none");
      } else {
        grid.innerHTML = "";
        noMsg?.classList.remove("d-none");
      }
    }
  } catch {
    /* non-critical */
  }

  // Load store items
  try {
    const itemsResult = await apiRequest("/api/v1/store/items?limit=100");
    const items = itemsResult.data || itemsResult;
    const grid = document.getElementById("storeItemGrid");
    const noMsg = document.getElementById("noItemsMsg");
    if (grid) {
      if (items.length) {
        grid.innerHTML = "";
        const balance = Number(me?.balance || 0);
        items.forEach((item, index) => {
          const price = Number(item.price);
          const canAfford = me && balance >= price;
          grid.insertAdjacentHTML(
            "beforeend",
            `<div class="col-sm-6 col-lg-4">
              <div class="store-item-card h-100 p-3 fade-in-up" style="animation-delay:${index * 60}ms">
                <h5 class="item-name mb-1">${item.name}</h5>
                <div class="item-price text-silver fw-bold fs-5 mb-3">$${price.toFixed(2)}</div>
                <div class="d-flex gap-2 mt-auto">
                  <button class="btn btn-outline-silver btn-sm flex-fill"
                    ${canAfford ? "" : "disabled"}
                    title="${me ? (canAfford ? "" : "Insufficient balance") : "Login to purchase"}"
                    onclick="storePageBuyWithBalance('${item.id}')">
                    Pay with Balance
                  </button>
                  <button class="btn btn-silver btn-sm flex-fill"
                    ${me ? "" : "disabled title='Login to purchase'"}
                    onclick="storePageBuyItem('${item.id}')">
                    Pay with Card
                  </button>
                </div>
              </div>
            </div>`,
          );
        });
        noMsg?.classList.add("d-none");
      } else {
        grid.innerHTML = "";
        noMsg?.classList.remove("d-none");
      }
    }
  } catch {
    /* non-critical */
  }

  // Add credits button → custom amount modal
  document.getElementById("addCreditsBtn")?.addEventListener("click", () => {
    const modal = new bootstrap.Modal(document.getElementById("customTopupModal"));
    modal.show();
  });

  document.getElementById("customTopupSubmit")?.addEventListener("click", async () => {
    const amount = Number(document.getElementById("customTopupAmount").value);
    const errEl = document.getElementById("customTopupError");
    if (!amount || amount < 1) {
      if (errEl) { errEl.textContent = "Enter a valid amount (min $1.00)"; errEl.classList.remove("d-none"); }
      return;
    }
    errEl?.classList.add("d-none");
    try {
      const data = await apiRequest("/api/v1/payments/topup", "POST", { amount });
      window.location.href = data.url;
    } catch (error) {
      if (errEl) { errEl.textContent = error.message; errEl.classList.remove("d-none"); }
    }
  });
}

async function topupWithPackage(amount) {
  try {
    const data = await apiRequest("/api/v1/payments/topup", "POST", { amount });
    window.location.href = data.url;
  } catch (error) {
    alert(error.message);
  }
}

async function storePageBuyWithBalance(itemId) {
  try {
    await apiRequest("/api/v1/store/buy", "POST", { itemId });
    const me = await fetchCurrentUser();
    currentUser = me;
    await initStorePage(me);
  } catch (error) {
    alert(error.message);
  }
}

async function storePageBuyItem(itemId) {
  try {
    const data = await apiRequest("/api/v1/payments/create-checkout-session", "POST", { itemId });
    window.location.href = data.url;
  } catch (error) {
    alert(error.message);
  }
}

// -----------------------------------------------------------
// HOME PAGE � server status widget
// -----------------------------------------------------------

// Set your CFX server code here (e.g. "abc123" from cfx.re/join/abc123)
// Leave empty to skip live polling and show a static online indicator.
const SILVERSHADE_CFX_CODE = "";

function initHomePage() {
  refreshServerStatus();
  if (SILVERSHADE_CFX_CODE) {
    setInterval(refreshServerStatus, 30000);
  }
}

async function refreshServerStatus() {
  const dot = document.getElementById("heroStatusDot");
  const playerCountEl = document.getElementById("heroPlayerCount");

  if (!SILVERSHADE_CFX_CODE) {
    // Static fallback � no CFX code configured
    if (dot) { dot.classList.remove("dot-offline"); dot.classList.add("dot-online"); }
    if (playerCountEl) playerCountEl.textContent = "� / 64";
    return;
  }

  try {
    const res = await fetch(
      `https://servers-frontend.fivem.net/api/servers/single/${SILVERSHADE_CFX_CODE}`,
      { signal: AbortSignal.timeout(8000) }
    );
    if (!res.ok) throw new Error("offline");
    const json = await res.json();
    const clients = json?.Data?.clients ?? 0;
    const maxClients = json?.Data?.sv_maxclients ?? 64;
    if (dot) { dot.classList.remove("dot-offline"); dot.classList.add("dot-online"); }
    if (playerCountEl) playerCountEl.textContent = `${clients} / ${maxClients}`;
  } catch {
    if (dot) { dot.classList.remove("dot-online"); dot.classList.add("dot-offline"); }
    if (playerCountEl) playerCountEl.textContent = "Offline";
  }
}
