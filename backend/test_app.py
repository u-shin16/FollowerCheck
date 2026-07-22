import unittest
from unittest.mock import patch

import app as app_module


class CheckEndpointTest(unittest.TestCase):
    def setUp(self):
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()

    def test_follow_back_candidates_use_account_key_before_urlname(self):
        creator = {
            "urlname": "me",
            "nickname": "Me",
            "profileImageUrl": None,
            "followingCount": 3,
            "followerCount": 3,
        }
        followings = [
            {"key": "same-user", "urlname": "old_name", "nickname": "Already Mutual"},
            {"id": 101, "urlname": "old_id_name", "nickname": "Already Mutual By Id"},
            {"key": "following-only", "urlname": "following_only", "nickname": "Following Only"},
        ]
        followers = [
            {"key": "same-user", "urlname": "new_name", "nickname": "Already Mutual"},
            {"id": 101, "urlname": "new_id_name", "nickname": "Already Mutual By Id"},
            {"key": "follower-only", "urlname": "follower_only", "nickname": "Follower Only"},
        ]

        def fake_fetch_all(_session, _urlname, kind):
            if kind == "followings":
                return followings, len(followings)
            return followers, len(followers)

        with patch.object(app_module, "fetch_creator", return_value=creator), patch.object(
            app_module, "fetch_all_follows", side_effect=fake_fetch_all
        ):
            response = self.client.get("/api/check?username=me")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["toFollowBack"], [])
        self.assertEqual([account["urlname"] for account in data["notFollowingBack"]], ["following_only"])
        self.assertFalse(data["toFollowBackReliable"])
        self.assertTrue(data["notFollowingBackReliable"])

    def test_follow_back_candidates_normalize_urlname_case(self):
        creator = {
            "urlname": "me",
            "nickname": "Me",
            "profileImageUrl": None,
            "followingCount": 1,
            "followerCount": 1,
        }
        followings = [{"urlname": "MixedCase", "nickname": "Mutual"}]
        followers = [{"urlname": "mixedcase", "nickname": "Mutual"}]

        def fake_fetch_all(_session, _urlname, kind):
            if kind == "followings":
                return followings, len(followings)
            return followers, len(followers)

        with patch.object(app_module, "fetch_creator", return_value=creator), patch.object(
            app_module, "fetch_all_follows", side_effect=fake_fetch_all
        ):
            response = self.client.get("/api/check?username=me")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["toFollowBack"], [])
        self.assertEqual(data["notFollowingBack"], [])

    def test_follow_back_candidates_are_suppressed_when_followings_are_capped(self):
        creator = {
            "urlname": "me",
            "nickname": "Me",
            "profileImageUrl": None,
            "followingCount": 601,
            "followerCount": 1,
        }
        followings = [{"key": "known-following", "urlname": "known_following"}]
        followers = [{"key": "maybe-already-followed", "urlname": "maybe_already_followed"}]

        def fake_fetch_all(_session, _urlname, kind):
            if kind == "followings":
                return followings, 600
            return followers, len(followers)

        with patch.object(app_module, "fetch_creator", return_value=creator), patch.object(
            app_module, "fetch_all_follows", side_effect=fake_fetch_all
        ):
            response = self.client.get("/api/check?username=me")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["toFollowBack"], [])
        self.assertFalse(data["toFollowBackReliable"])
        self.assertTrue(data["notFollowingBackReliable"])

    def test_not_following_back_is_suppressed_when_followers_are_capped(self):
        creator = {
            "urlname": "me",
            "nickname": "Me",
            "profileImageUrl": None,
            "followingCount": 1,
            "followerCount": 601,
        }
        followings = [{"key": "maybe-already-follower", "urlname": "maybe_already_follower"}]
        followers = [{"key": "known-follower", "urlname": "known_follower"}]

        def fake_fetch_all(_session, _urlname, kind):
            if kind == "followings":
                return followings, len(followings)
            return followers, 600

        with patch.object(app_module, "fetch_creator", return_value=creator), patch.object(
            app_module, "fetch_all_follows", side_effect=fake_fetch_all
        ):
            response = self.client.get("/api/check?username=me")

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["notFollowingBack"], [])
        self.assertFalse(data["notFollowingBackReliable"])
        self.assertFalse(data["toFollowBackReliable"])

    def test_authenticated_check_removes_already_followed_candidate(self):
        creator = {
            "urlname": "me",
            "nickname": "Me",
            "profileImageUrl": None,
            "followingCount": 0,
            "followerCount": 1,
            "isMyself": False,
        }
        auth_creator = {**creator, "isMyself": True}
        followed_candidate = {
            "key": "already-followed",
            "urlname": "already_followed",
            "nickname": "Already Followed",
        }
        followers = [followed_candidate]

        def fake_fetch_creator(_session, urlname, headers=None):
            if urlname == "me" and headers and headers.get("Cookie") == "session=ok":
                return auth_creator
            if urlname == "me":
                return creator
            if urlname == "already_followed" and headers and headers.get("Cookie") == "session=ok":
                return {"urlname": urlname, "isFollowing": True, "isFollowed": False}
            return None

        def fake_fetch_all(_session, _urlname, kind):
            if kind == "followings":
                return [], 0
            return followers, len(followers)

        with patch.object(app_module, "fetch_creator", side_effect=fake_fetch_creator), patch.object(
            app_module, "fetch_all_follows", side_effect=fake_fetch_all
        ):
            response = self.client.post(
                "/api/check",
                json={"username": "me", "cookieHeader": "session=ok"},
            )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["toFollowBack"], [])
        self.assertTrue(data["authenticatedCheck"])

    def test_authenticated_check_keeps_candidate_i_do_not_follow(self):
        creator = {
            "urlname": "me",
            "nickname": "Me",
            "profileImageUrl": None,
            "followingCount": 0,
            "followerCount": 1,
            "isMyself": False,
        }
        auth_creator = {**creator, "isMyself": True}
        candidate = {
            "key": "not-followed",
            "urlname": "not_followed",
            "nickname": "Not Followed",
        }

        def fake_fetch_creator(_session, urlname, headers=None):
            if urlname == "me" and headers and headers.get("Cookie") == "session=ok":
                return auth_creator
            if urlname == "me":
                return creator
            if urlname == "not_followed" and headers and headers.get("Cookie") == "session=ok":
                return {"urlname": urlname, "isFollowing": False, "isFollowed": False}
            return None

        def fake_fetch_all(_session, _urlname, kind):
            if kind == "followings":
                return [], 0
            return [candidate], 1

        with patch.object(app_module, "fetch_creator", side_effect=fake_fetch_creator), patch.object(
            app_module, "fetch_all_follows", side_effect=fake_fetch_all
        ):
            response = self.client.post(
                "/api/check",
                json={"username": "me", "cookieHeader": "session=ok"},
            )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual([account["urlname"] for account in data["toFollowBack"]], ["not_followed"])
        self.assertTrue(data["toFollowBackReliable"])
        self.assertTrue(data["authenticatedCheck"])

    def test_authenticated_check_removes_account_that_follows_me_back(self):
        creator = {
            "urlname": "me",
            "nickname": "Me",
            "profileImageUrl": None,
            "followingCount": 1,
            "followerCount": 0,
            "isMyself": False,
        }
        auth_creator = {**creator, "isMyself": True}
        mutual_candidate = {
            "key": "already-follows-me",
            "urlname": "already_follows_me",
            "nickname": "Already Follows Me",
        }
        followings = [mutual_candidate]

        def fake_fetch_creator(_session, urlname, headers=None):
            if urlname == "me" and headers and headers.get("Cookie") == "session=ok":
                return auth_creator
            if urlname == "me":
                return creator
            if urlname == "already_follows_me" and headers and headers.get("Cookie") == "session=ok":
                return {"urlname": urlname, "isFollowing": False, "isFollowed": True}
            return None

        def fake_fetch_all(_session, _urlname, kind):
            if kind == "followings":
                return followings, len(followings)
            return [], 0

        with patch.object(app_module, "fetch_creator", side_effect=fake_fetch_creator), patch.object(
            app_module, "fetch_all_follows", side_effect=fake_fetch_all
        ):
            response = self.client.post(
                "/api/check",
                json={"username": "me", "cookieHeader": "session=ok"},
            )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["notFollowingBack"], [])
        self.assertTrue(data["authenticatedCheck"])

    def test_cookie_for_different_account_is_not_used_for_candidate_filtering(self):
        creator = {
            "urlname": "me",
            "nickname": "Me",
            "profileImageUrl": None,
            "followingCount": 0,
            "followerCount": 1,
            "isMyself": False,
        }
        follower = {
            "key": "candidate",
            "urlname": "candidate",
            "nickname": "Candidate",
        }

        def fake_fetch_creator(_session, urlname, headers=None):
            if urlname == "me":
                return creator
            if urlname == "candidate" and headers and headers.get("Cookie") == "session=other":
                return {"urlname": urlname, "isFollowing": True}
            return None

        def fake_fetch_all(_session, _urlname, kind):
            if kind == "followings":
                return [], 0
            return [follower], 1

        with patch.object(app_module, "fetch_creator", side_effect=fake_fetch_creator), patch.object(
            app_module, "fetch_all_follows", side_effect=fake_fetch_all
        ):
            response = self.client.post(
                "/api/check",
                json={"username": "me", "cookieHeader": "session=other"},
            )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["toFollowBack"], [])
        self.assertFalse(data["authenticatedCheck"])
        self.assertFalse(data["toFollowBackReliable"])
        self.assertTrue(data["toFollowBackUnavailableReason"])
        self.assertTrue(data["authWarning"])


if __name__ == "__main__":
    unittest.main()
