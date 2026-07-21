import io
import os
import re
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from flask import Flask, jsonify, request, send_file, send_from_directory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")
EXTENSION_DIR = os.path.join(BASE_DIR, "..", "extension")
app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")

NOTE_API_BASE = "https://note.com/api/v2/creators"
NOTE_FOLLOW_API_BASE = "https://note.com/api/v3/users"
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; YouMitonde/1.0)"}
REQUEST_TIMEOUT = 10
MAX_WORKERS = 5
MAX_PAGES = 100  # safety cap; note.com itself caps lists around 600 items (50 pages)
FOLLOW_ACTION_DELAY_SECONDS = 2.5  # note.com 429s a burst of follow/unfollow calls; space them out
MAX_FOLLOW_ACTION_TARGETS = 200  # guard against accidental/huge batch requests


class NoteApiError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.message = message
        self.status = status


def normalize_username(raw):
    raw = raw.strip()
    raw = re.sub(r"^https?://(www\.)?note\.com/", "", raw)
    raw = raw.lstrip("@")
    raw = raw.strip("/")
    raw = raw.split("/")[0].split("?")[0]
    return raw


def fetch_creator(session, urlname):
    resp = session.get(f"{NOTE_API_BASE}/{urlname}", headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        raise NoteApiError(f"note.comへの問い合わせに失敗しました（status {resp.status_code}）")
    return resp.json().get("data")


def fetch_follow_page(session, urlname, kind, page):
    resp = session.get(
        f"{NOTE_API_BASE}/{urlname}/{kind}",
        params={"page": page},
        headers=REQUEST_HEADERS,
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code != 200:
        raise NoteApiError(f"{kind}の取得に失敗しました（status {resp.status_code}）")
    data = resp.json().get("data")
    if isinstance(data, list):
        # note.com returns {"data": []} instead of the usual object shape
        # once a list is empty or a page is requested past the end.
        return [], 0, True
    return data.get("follows", []), data.get("totalCount", 0), data.get("isLastPage", True)


def fetch_all_follows(session, urlname, kind):
    follows, total, is_last = fetch_follow_page(session, urlname, kind, 1)
    if is_last or not follows:
        return follows, total

    page_size = len(follows)
    total_pages = min(-(-total // page_size), MAX_PAGES)  # ceil division, safety-capped
    results = {1: follows}

    def worker(page):
        time.sleep(0.05)
        items, _, _ = fetch_follow_page(session, urlname, kind, page)
        return page, items

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(worker, page) for page in range(2, total_pages + 1)]
        for future in as_completed(futures):
            page, items = future.result()
            results[page] = items

    all_follows = []
    for page in sorted(results):
        all_follows.extend(results[page])
    return all_follows, total


def to_account(entry):
    urlname = entry.get("urlname")
    return {
        "key": entry.get("key"),
        "urlname": urlname,
        "name": entry.get("nickname") or entry.get("name") or urlname,
        "profileImage": entry.get("userProfileImagePath"),
        "noteUrl": f"https://note.com/{urlname}",
    }


@app.get("/api/creator/<urlname>")
def creator_detail(urlname):
    session = requests.Session()
    try:
        creator = fetch_creator(session, urlname)
    except NoteApiError as exc:
        return jsonify({"error": exc.message}), exc.status
    except requests.RequestException:
        return jsonify({"error": "note.comへの接続に失敗しました。時間をおいてもう一度お試しください"}), 502

    if creator is None:
        return jsonify({"error": f"ユーザー「{urlname}」が見つかりませんでした"}), 404

    return jsonify(
        {
            "urlname": creator.get("urlname"),
            "name": creator.get("nickname"),
            "profile": creator.get("profile"),
            "profileImage": creator.get("profileImageUrl"),
            "followingCount": creator.get("followingCount") or 0,
            "followerCount": creator.get("followerCount") or 0,
            "noteCount": creator.get("noteCount") or 0,
        }
    )


@app.get("/api/check")
def check():
    urlname = normalize_username(request.args.get("username", ""))
    if not urlname:
        return jsonify({"error": "noteのユーザー名を入力してください"}), 400

    session = requests.Session()
    try:
        creator = fetch_creator(session, urlname)
        if creator is None:
            return jsonify({"error": f"ユーザー「{urlname}」が見つかりませんでした"}), 404

        followings, followings_total = fetch_all_follows(session, urlname, "followings")
        followers, followers_total = fetch_all_follows(session, urlname, "followers")
    except NoteApiError as exc:
        return jsonify({"error": exc.message}), exc.status
    except requests.RequestException:
        return jsonify({"error": "note.comへの接続に失敗しました。時間をおいてもう一度お試しください"}), 502

    follower_urlnames = {f.get("urlname") for f in followers}
    following_urlnames = {f.get("urlname") for f in followings}

    not_following_back = [
        to_account(f) for f in followings if f.get("urlname") not in follower_urlnames
    ]
    not_following_back.sort(key=lambda account: account["name"])

    to_follow_back = [
        to_account(f) for f in followers if f.get("urlname") not in following_urlnames
    ]
    to_follow_back.sort(key=lambda account: account["name"])

    follower_count = creator.get("followerCount") or 0
    following_count = creator.get("followingCount") or 0
    capped = (
        (follower_count > 0 and follower_count > followers_total)
        or (following_count > 0 and following_count > followings_total)
    )

    return jsonify(
        {
            "creator": {
                "urlname": creator.get("urlname"),
                "name": creator.get("nickname"),
                "profileImage": creator.get("profileImageUrl"),
                "followingCount": following_count,
                "followerCount": follower_count,
            },
            "checkedFollowingCount": len(followings),
            "checkedFollowerCount": len(followers),
            "notFollowingBack": not_following_back,
            "toFollowBack": to_follow_back,
            "capped": capped,
        }
    )


def parse_follow_action_request():
    payload = request.get_json(silent=True) or {}
    cookie_header = (payload.get("cookieHeader") or "").strip()
    targets = payload.get("targets") or []

    if not cookie_header:
        return None, None, (jsonify({"error": "note.comのCookie文字列を入力してください"}), 400)
    if not targets:
        return None, None, (jsonify({"error": "対象が選択されていません"}), 400)
    if len(targets) > MAX_FOLLOW_ACTION_TARGETS:
        return None, None, (
            jsonify({"error": f"一度に処理できるのは{MAX_FOLLOW_ACTION_TARGETS}件までです"}),
            400,
        )
    return cookie_header, targets, None


def perform_follow_action(cookie_header, targets, method):
    # NOTE: /api/v3/users/{key}/following is not officially documented by note.com.
    # Reverse-engineered from a live captured request: the path segment is the
    # creator's hex "key" (not the numeric "id"), auth is the full note.com
    # cookie jar (session cookie + note_gql_auth_token together), and
    # X-Requested-With: XMLHttpRequest is required or note.com returns 422.
    session = requests.Session()
    headers = {
        **REQUEST_HEADERS,
        "Referer": "https://note.com/",
        "Origin": "https://note.com",
        "X-Requested-With": "XMLHttpRequest",
        "Cookie": cookie_header,
    }

    results = []
    for index, target in enumerate(targets):
        key = target.get("key")
        urlname = target.get("urlname")

        if index > 0:
            time.sleep(FOLLOW_ACTION_DELAY_SECONDS)

        if not key:
            results.append({"urlname": urlname, "success": False, "error": "keyが取得できませんでした"})
            continue

        url = f"{NOTE_FOLLOW_API_BASE}/{key}/following"
        resp = None
        error = None

        try:
            resp = session.request(method, url, headers=headers, timeout=REQUEST_TIMEOUT)
        except requests.RequestException:
            error = "note.comへの接続に失敗しました"

        if error:
            results.append({"urlname": urlname, "success": False, "error": error})
            continue

        if resp.status_code == 429:
            results.append(
                {
                    "urlname": urlname,
                    "success": False,
                    "error": "note.comのレート制限に達しました。数分〜数十分単位のクールダウンが必要な場合があるので、5〜10分ほど間隔を空けて件数を減らして試してください",
                }
            )
            continue

        if resp.status_code in (401, 403):
            results.append(
                {"urlname": urlname, "success": False, "error": "認証に失敗しました。Cookieが正しいか確認してください"}
            )
            continue

        ok = resp.status_code in (200, 201, 204)
        results.append(
            {
                "urlname": urlname,
                "success": ok,
                "error": None if ok else f"note.comがstatus {resp.status_code}を返しました",
            }
        )

    return results


@app.post("/api/unfollow")
def unfollow():
    cookie_header, targets, error = parse_follow_action_request()
    if error:
        return error
    return jsonify({"results": perform_follow_action(cookie_header, targets, "DELETE")})


@app.post("/api/follow")
def follow():
    cookie_header, targets, error = parse_follow_action_request()
    if error:
        return error
    return jsonify({"results": perform_follow_action(cookie_header, targets, "POST")})


@app.get("/extension.zip")
def download_extension():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for root, _dirs, files in os.walk(EXTENSION_DIR):
            for filename in files:
                if filename == ".DS_Store":
                    continue
                file_path = os.path.join(root, filename)
                zip_file.write(file_path, arcname=os.path.relpath(file_path, EXTENSION_DIR))
    buffer.seek(0)
    return send_file(
        buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name="youmitonde-helper-extension.zip",
    )


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


if __name__ == "__main__":
    # Debug mode is kept off on purpose: this process handles the user's note.com
    # session cookie, and Werkzeug's interactive debugger is a known RCE risk.
    app.run(host="127.0.0.1", port=5000, debug=False)
