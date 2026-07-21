const SESSION_COOKIE_NAME = "_note_session_v5";

const button = document.getElementById("copy-btn");
const status = document.getElementById("status");

button.addEventListener("click", async () => {
  status.className = "";
  status.textContent = "確認中…";

  try {
    const cookies = await chrome.cookies.getAll({ domain: "note.com" });

    if (!cookies.some((c) => c.name === SESSION_COOKIE_NAME)) {
      status.className = "error";
      status.textContent = "ログインCookieが見つかりませんでした。note.comにログインしているか確認してください";
      return;
    }

    const cookieHeader = cookies.map((c) => `${c.name}=${c.value}`).join("; ");
    await navigator.clipboard.writeText(cookieHeader);
    status.className = "success";
    status.textContent = "コピーしました！アプリの入力欄に貼り付けてください";
  } catch (err) {
    status.className = "error";
    status.textContent = "コピーに失敗した: " + err.message;
  }
});
