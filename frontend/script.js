const form = document.getElementById("check-form");
const input = document.getElementById("username-input");
const button = document.getElementById("check-button");
const statusEl = document.getElementById("status");
const resultEl = document.getElementById("result");
const profileCard = document.getElementById("profile-card");
const cappedWarning = document.getElementById("capped-warning");
const cookiePanel = document.getElementById("cookie-panel");
const cookieInput = document.getElementById("cookie-input");
const cookieHelpToggle = document.getElementById("cookie-help-toggle");
const cookieHelpBody = document.getElementById("cookie-help-body");

cookieHelpToggle.addEventListener("click", () => {
  cookieHelpBody.hidden = !cookieHelpBody.hidden;
  cookieHelpToggle.classList.toggle("open", !cookieHelpBody.hidden);
});

const DEFAULT_AVATAR =
  "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 56 56'><rect width='56' height='56' rx='28' fill='%23dbe4e1'/></svg>";

const modalOverlay = document.getElementById("account-modal-overlay");
const modalBody = document.getElementById("modal-body");
const modalClose = document.getElementById("modal-close");

modalClose.addEventListener("click", closeModal);
modalOverlay.addEventListener("click", (event) => {
  if (event.target === modalOverlay) closeModal();
});
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (!confirmOverlay.hidden) {
    resolveConfirm(false);
    return;
  }
  if (!modalOverlay.hidden) closeModal();
});

function closeModal() {
  modalOverlay.hidden = true;
  modalBody.innerHTML = "";
}

const confirmOverlay = document.getElementById("confirm-modal-overlay");
const confirmMessageEl = document.getElementById("confirm-modal-message");
const confirmOkButton = document.getElementById("confirm-modal-ok");
const confirmCancelButton = document.getElementById("confirm-modal-cancel");
let confirmResolve = null;

function showConfirm(message) {
  confirmMessageEl.textContent = message;
  confirmOverlay.hidden = false;
  return new Promise((resolve) => {
    confirmResolve = resolve;
  });
}

function resolveConfirm(result) {
  confirmOverlay.hidden = true;
  if (confirmResolve) {
    confirmResolve(result);
    confirmResolve = null;
  }
}

confirmOkButton.addEventListener("click", () => resolveConfirm(true));
confirmCancelButton.addEventListener("click", () => resolveConfirm(false));
confirmOverlay.addEventListener("click", (event) => {
  if (event.target === confirmOverlay) resolveConfirm(false);
});

async function openAccountModal(account, endpoint, actionVerb, onResolved) {
  const actionType = endpoint === "/api/unfollow" ? "unfollow" : "follow";
  modalOverlay.hidden = false;
  modalBody.innerHTML = renderModalProfile(account, null, "読み込み中…");

  let detail = null;
  try {
    const res = await fetch(`/api/creator/${encodeURIComponent(account.urlname)}`);
    if (res.ok) detail = await res.json();
  } catch (err) {
    // ネットワークエラー時も最低限の情報だけで表示を続ける
  }

  modalBody.innerHTML = renderModalProfile(account, detail, null);

  const actionButton = document.getElementById("modal-action-button");
  const actionStatus = document.getElementById("modal-action-status");
  const actionClass = endpoint === "/api/unfollow" ? "danger" : "primary";
  actionButton.classList.add(actionClass);

  actionButton.addEventListener("click", async () => {
    if (activeAction && activeAction !== actionType) {
      actionStatus.hidden = false;
      actionStatus.className = "modal-status error";
      actionStatus.textContent = "他の処理が完了するまでお待ちください";
      return;
    }

    if (!cookieInput.value.trim()) {
      actionStatus.hidden = false;
      actionStatus.className = "modal-status error";
      actionStatus.textContent = "先にCookieを入力してください";
      return;
    }

    const confirmed = await showConfirm(
      `${account.name}を${actionVerb}します。よろしいですか？\n（note.com非公式の仕組みを使っているため、失敗する場合もあります）`
    );
    if (!confirmed) return;

    actionButton.disabled = true;
    actionStatus.hidden = false;
    actionStatus.className = "modal-status";
    actionStatus.textContent = "処理中…";
    beginAction(actionType);

    try {
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          cookieHeader: cookieInput.value.trim(),
          targets: [{ key: account.key, urlname: account.urlname }],
        }),
      });
      const data = await res.json();

      if (!res.ok) {
        actionStatus.className = "modal-status error";
        actionStatus.textContent = data.error || `${actionVerb}に失敗しました`;
        actionButton.disabled = false;
        return;
      }

      const result = data.results[0];
      if (onResolved) onResolved([result]);

      if (result.success) {
        actionStatus.className = "modal-status";
        actionStatus.textContent = "完了しました";
        setTimeout(closeModal, 800);
      } else {
        actionStatus.className = "modal-status error";
        actionStatus.textContent = result.error || "失敗しました";
        actionButton.disabled = false;
      }
    } catch (err) {
      actionStatus.className = "modal-status error";
      actionStatus.textContent = "通信に失敗しました";
      actionButton.disabled = false;
    } finally {
      endAction();
    }
  });

  function renderModalProfile(acc, info, loadingMessage) {
    const stats = info
      ? `<div class="modal-profile__stats">フォロー中 ${info.followingCount.toLocaleString()} ・ フォロワー ${info.followerCount.toLocaleString()} ・ 記事 ${info.noteCount.toLocaleString()}</div>`
      : "";
    const bio = info && info.profile ? `<p class="modal-profile__bio">${escapeHtml(info.profile)}</p>` : "";
    const loading = loadingMessage ? `<p class="modal-status">${escapeHtml(loadingMessage)}</p>` : "";

    return `
      <div class="modal-profile">
        <img src="${acc.profileImage || DEFAULT_AVATAR}" alt="${escapeHtml(acc.name)}">
        <div class="modal-profile__name">${escapeHtml(acc.name)}</div>
        ${stats}
        ${bio}
        ${loading}
        <a class="modal-profile__link" href="${acc.noteUrl}" target="_blank" rel="noopener noreferrer">note.comで開く ↗</a>
        <div class="modal-actions">
          <button type="button" id="modal-action-button" class="modal-action-button">${actionVerb}する</button>
          <p id="modal-action-status" class="modal-status" hidden></p>
        </div>
      </div>
    `;
  }
}

function createAccountPanel({
  sectionId,
  bodyId,
  toggleId,
  listId,
  selectAllId,
  buttonId,
  statusId,
  emptyId,
  endpoint,
  actionVerb,
}) {
  const sectionEl = document.getElementById(sectionId);
  const bodyEl = document.getElementById(bodyId);
  const toggleEl = document.getElementById(toggleId);
  const listEl = document.getElementById(listId);
  const selectAllEl = document.getElementById(selectAllId);
  const buttonEl = document.getElementById(buttonId);
  const panelStatusEl = document.getElementById(statusId);
  const emptyEl = document.getElementById(emptyId);
  const actionType = endpoint === "/api/unfollow" ? "unfollow" : "follow";
  let accounts = [];
  let blocked = false;

  toggleEl.addEventListener("click", () => {
    bodyEl.hidden = !bodyEl.hidden;
    toggleEl.textContent = bodyEl.hidden ? "表示する" : "隠す";
  });

  function updateButtonState() {
    const anySelected = listEl.querySelectorAll(".account-checkbox:checked").length > 0;
    const hasCookie = cookieInput.value.trim().length > 0;
    buttonEl.disabled = blocked || !(anySelected && hasCookie);
  }

  function setBlocked(next) {
    blocked = next;
    bodyEl.classList.toggle("blocked", blocked);
    updateButtonState();
  }

  selectAllEl.addEventListener("change", () => {
    listEl.querySelectorAll(".account-checkbox").forEach((checkbox) => (checkbox.checked = selectAllEl.checked));
    updateButtonState();
  });

  listEl.addEventListener("change", (event) => {
    if (event.target.classList.contains("account-checkbox")) updateButtonState();
  });

  listEl.addEventListener("click", (event) => {
    const link = event.target.closest("a");
    if (!link) return;
    event.preventDefault();
    if (blocked) return;
    const urlname = link.closest("li").dataset.urlname;
    const account = accounts.find((a) => a.urlname === urlname);
    if (account) openAccountModal(account, endpoint, actionVerb, applyResults);
  });

  buttonEl.addEventListener("click", async () => {
    const selected = [...listEl.querySelectorAll(".account-checkbox:checked")];
    const targets = selected.map((checkbox) => {
      const account = accounts.find((a) => a.urlname === checkbox.dataset.urlname);
      return { key: account.key, urlname: account.urlname };
    });
    if (targets.length === 0) return;

    const confirmed = await showConfirm(
      `${targets.length}件を${actionVerb}します。よろしいですか？\n（note.com非公式の仕組みを使っているため、失敗する場合もあります）`
    );
    if (!confirmed) return;

    buttonEl.disabled = true;
    panelStatusEl.hidden = false;
    panelStatusEl.className = "status";
    panelStatusEl.textContent = `処理中…（${targets.length}件）`;
    beginAction(actionType);

    try {
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ cookieHeader: cookieInput.value.trim(), targets }),
      });
      const data = await res.json();

      if (!res.ok) {
        panelStatusEl.className = "status error";
        panelStatusEl.textContent = data.error || `${actionVerb}に失敗しました`;
        return;
      }

      applyResults(data.results);
      const successCount = data.results.filter((r) => r.success).length;
      panelStatusEl.className = "status";
      panelStatusEl.textContent = `${successCount}/${data.results.length}件の${actionVerb}に成功しました`;
    } catch (err) {
      panelStatusEl.className = "status error";
      panelStatusEl.textContent = "通信に失敗しました。時間をおいてもう一度お試しください";
    } finally {
      endAction();
    }
  });

  function applyResults(results) {
    results.forEach((result) => {
      const row = listEl.querySelector(`li[data-urlname="${cssEscape(result.urlname)}"]`);
      if (!row) return;

      const rowStatus = row.querySelector(".row-status");
      if (result.success) {
        row.classList.add("done");
        row.querySelector(".account-checkbox").disabled = true;
        row.querySelector(".account-checkbox").checked = false;
        rowStatus.textContent = "完了";
        rowStatus.classList.remove("error");
      } else {
        rowStatus.textContent = result.error || "失敗";
        rowStatus.classList.add("error");
      }
    });
  }

  return {
    render(newAccounts) {
      accounts = newAccounts;
      selectAllEl.checked = false;
      panelStatusEl.hidden = true;
      bodyEl.hidden = true;
      toggleEl.textContent = "表示する";

      if (newAccounts.length === 0) {
        sectionEl.hidden = true;
        emptyEl.hidden = false;
        return false;
      }

      emptyEl.hidden = true;
      sectionEl.hidden = false;
      listEl.innerHTML = newAccounts
        .map(
          (account) => `
          <li data-urlname="${escapeHtml(account.urlname)}">
            <input type="checkbox" class="account-checkbox" data-urlname="${escapeHtml(account.urlname)}">
            <img src="${account.profileImage || DEFAULT_AVATAR}" alt="${escapeHtml(account.name)}">
            <a href="${account.noteUrl}" target="_blank" rel="noopener noreferrer">${escapeHtml(account.name)}</a>
            <span class="row-status"></span>
          </li>
        `
        )
        .join("");
      updateButtonState();
      return true;
    },
    refreshButtonState: updateButtonState,
    setBlocked,
  };
}

const unfollowPanel = createAccountPanel({
  sectionId: "not-following-back-section",
  bodyId: "not-following-back-body",
  toggleId: "not-following-back-toggle",
  listId: "not-following-back-list",
  selectAllId: "select-all-unfollow",
  buttonId: "unfollow-button",
  statusId: "unfollow-status",
  emptyId: "empty-not-following-back",
  endpoint: "/api/unfollow",
  actionVerb: "フォロー解除",
});

const followPanel = createAccountPanel({
  sectionId: "to-follow-back-section",
  bodyId: "to-follow-back-body",
  toggleId: "to-follow-back-toggle",
  listId: "to-follow-back-list",
  selectAllId: "select-all-follow",
  buttonId: "follow-button",
  statusId: "follow-status",
  emptyId: "empty-to-follow-back",
  endpoint: "/api/follow",
  actionVerb: "フォロー",
});

let activeAction = null;

function beginAction(type) {
  activeAction = type;
  // Only block the opposite panel; the active panel disables its own
  // button directly, and re-running its updateButtonState here would
  // undo that.
  if (type === "follow") {
    unfollowPanel.setBlocked(true);
  } else {
    followPanel.setBlocked(true);
  }
}

function endAction() {
  activeAction = null;
  unfollowPanel.setBlocked(false);
  followPanel.setBlocked(false);
}

cookieInput.addEventListener("input", () => {
  unfollowPanel.refreshButtonState();
  followPanel.refreshButtonState();
});

const USERNAME_HISTORY_KEY = "youmitonde:usernameHistory";
const USERNAME_HISTORY_MAX = 5;
const usernameHistoryList = document.getElementById("username-history");

function loadUsernameHistory() {
  try {
    const raw = JSON.parse(localStorage.getItem(USERNAME_HISTORY_KEY));
    return Array.isArray(raw) ? raw : [];
  } catch (err) {
    return [];
  }
}

function renderUsernameHistory(history) {
  usernameHistoryList.innerHTML = history.map((name) => `<option value="${escapeHtml(name)}">`).join("");
}

function rememberUsername(username) {
  const history = [username, ...loadUsernameHistory().filter((name) => name !== username)].slice(
    0,
    USERNAME_HISTORY_MAX
  );
  localStorage.setItem(USERNAME_HISTORY_KEY, JSON.stringify(history));
  renderUsernameHistory(history);
}

const usernameHistory = loadUsernameHistory();
renderUsernameHistory(usernameHistory);
if (usernameHistory[0]) {
  input.value = usernameHistory[0];
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const username = input.value.trim();
  if (!username) return;

  rememberUsername(username);

  setLoading(true);
  hideAll();

  try {
    const res = await fetch(`/api/check?username=${encodeURIComponent(username)}`);
    const data = await res.json();

    if (!res.ok) {
      showError(data.error || "エラーが発生しました");
      return;
    }

    renderResult(data);
  } catch (err) {
    showError("通信に失敗しました。時間をおいてもう一度お試しください");
  } finally {
    setLoading(false);
  }
});

function setLoading(isLoading) {
  button.disabled = isLoading;
  button.textContent = isLoading ? "チェック中…" : "チェックする";
  if (isLoading) {
    statusEl.hidden = false;
    statusEl.className = "status";
    statusEl.textContent = "note.comを確認中です。フォローが多いと時間がかかる場合があります…";
  }
}

function hideAll() {
  resultEl.hidden = true;
  cappedWarning.hidden = true;
  cookiePanel.hidden = true;
  cookieInput.value = "";
  unfollowPanel.render([]);
  followPanel.render([]);
  profileCard.innerHTML = "";
}

function showError(message) {
  statusEl.hidden = false;
  statusEl.className = "status error";
  statusEl.textContent = message;
}

function renderResult(data) {
  statusEl.hidden = true;
  resultEl.hidden = false;

  const creator = data.creator;
  profileCard.innerHTML = `
    <img src="${creator.profileImage || DEFAULT_AVATAR}" alt="${escapeHtml(creator.name || "")}">
    <div>
      <div class="profile-card__name">${escapeHtml(creator.name || creator.urlname)}</div>
      <div class="profile-card__stats">
        フォロー中 ${creator.followingCount.toLocaleString()} ・ フォロワー ${creator.followerCount.toLocaleString()}
        （確認済み: フォロー中 ${data.checkedFollowingCount} 件 / フォロワー ${data.checkedFollowerCount} 件）
      </div>
    </div>
  `;

  if (data.capped) {
    cappedWarning.hidden = false;
  }

  const hasUnfollowTargets = unfollowPanel.render(data.notFollowingBack);
  const hasFollowTargets = followPanel.render(data.toFollowBack);
  cookiePanel.hidden = !(hasUnfollowTargets || hasFollowTargets);
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function cssEscape(str) {
  return window.CSS && CSS.escape ? CSS.escape(str) : String(str).replace(/"/g, '\\"');
}
