"""1:N identity and Face process JSON tests. No engine binary required."""

from __future__ import annotations

import base64
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "demo"))
sys.path.insert(0, str(_ROOT / "sdk"))

import identity
import ix_payload
import result_view


def _person(index: int, name: str, feature: str = "same"):
    return SimpleNamespace(id=index, name=name, feature=feature)


def _view(doc: dict) -> dict:
    return ix_payload.face_view(doc)


class IdentifyDocumentTests(unittest.TestCase):
    def test_hit_uses_gallery_id_not_list_position(self):
        people = [
            _person(7, "Ada", "a"),
            _person(12, "Bea", "b"),
        ]

        def scores(probe, stored):
            return {"a": 0.91, "b": 0.4}[stored]

        doc = identity.identify_document(
            {"feature": "probe", "faceRegion": {"x": 1, "y": 2, "width": 3, "height": 4}},
            people,
            0.67,
            scores,
        )
        self.assertIn("metadata", doc)
        self.assertNotIn("api", doc)
        self.assertEqual(doc["metadata"]["status"], 0)
        view = _view(doc)
        self.assertEqual(view["status"], 0)
        self.assertEqual(
            view["pairs"],
            [
                {
                    "leftFaceId": 0,
                    "rightFaceId": 0,
                    "leftImageId": 0,
                    "rightImageId": 7,
                    "score": 0.91,
                }
            ],
        )
        self.assertEqual(view["detects"][0]["faces"][0]["box"]["width"], 3)
        self.assertNotIn("faceId", view["detects"][0]["faces"][0])
        self.assertNotIn("similarity", view["pairs"][0])

    def test_threshold_uses_displayed_score(self):
        people = [_person(4, "Ada", "ada")]
        below = identity.identify_document(
            {"feature": "p"},
            people,
            0.993,
            lambda _probe, _stored: 0.99294,
        )
        self.assertEqual(_view(below)["pairs"], [])
        hit = identity.identify_document(
            {"feature": "p"},
            people,
            0.993,
            lambda _probe, _stored: 0.99296,
        )
        # 0.99296 displays as 0.9930, so a 0.9930 threshold is a hit.
        self.assertEqual(_view(hit)["pairs"][0]["score"], 0.993)

    def test_threshold_is_inclusive_and_best_is_first(self):
        people = [_person(2, "low", "2"), _person(9, "tie", "9"), _person(4, "high", "4")]

        def scores(_probe, stored):
            return {"2": 0.6699, "9": 0.67, "4": 0.88}[stored]

        doc = identity.identify_document({"feature": "p"}, people, 0.67, scores)
        pairs = _view(doc)["pairs"]
        self.assertEqual([row["rightImageId"] for row in pairs], [4, 9])
        self.assertEqual(pairs[0]["score"], 0.88)

    def test_no_match_keeps_empty_match_list(self):
        doc = identity.identify_document(
            {"feature": "p"},
            [_person(3, "Ada")],
            0.67,
            lambda _probe, _stored: 0.5,
        )
        view = _view(doc)
        self.assertEqual(view["status"], 0)
        self.assertEqual(view["pairs"], [])

    def test_uncomparable_templates_are_an_error(self):
        doc = identity.identify_document(
            {"feature": "p"},
            [_person(3, "Ada")],
            0.67,
            lambda _probe, _stored: -1,
        )
        view = _view(doc)
        self.assertEqual(doc["metadata"]["status"], -1)
        self.assertNotIn("api", doc)
        self.assertEqual(view["status"], -1)
        self.assertEqual(view["message"], "feature compare failed")

    def test_one_bad_template_does_not_hide_a_hit(self):
        people = [_person(1, "broken", "bad"), _person(8, "ok", "ok")]

        def scores(_probe, stored):
            return -1 if stored == "bad" else 0.8

        doc = identity.identify_document({"feature": "p"}, people, 0.67, scores)
        self.assertEqual(_view(doc)["pairs"][0]["rightImageId"], 8)

    def test_feature_bytes_strips_whitespace_and_data_url(self):
        raw = b"face-template-bytes"
        wrapped = "data:application/octet-stream;base64," + base64.b64encode(raw).decode()
        spaced = "\n".join(wrapped[i : i + 16] for i in range(0, len(wrapped), 16))
        self.assertEqual(identity.feature_bytes(spaced), raw)

    def test_wrap_process_uses_identixia_envelope(self):
        env = ix_payload.wrap_process(
            {
                "status": 0,
                "message": "COMPLETED",
                "data": [
                    {
                        "faceId": 1,
                        "faceRegion": {"x": 0, "y": 0, "width": 2, "height": 3},
                        "attributes": {"Age": {"value": 40}, "Deepfake": {"value": "REAL"}},
                    }
                ],
                "match": [{"firstFaceId": 0, "secondFaceId": 1, "similarity": 0.5}],
            }
        )
        self.assertIn("metadata", env)
        self.assertEqual(env["metadata"]["status"], 0)
        self.assertNotIn("api", env)
        self.assertNotIn("result", env)
        face = env["faces"][0]
        pair = env["pairs"][0]
        self.assertEqual(face["id"], 1)
        self.assertEqual(face["box"]["width"], 2)
        self.assertEqual(face["traits"]["ageYears"]["value"], 40)
        self.assertEqual(face["traits"]["deepfake"]["value"], "REAL")
        self.assertEqual(pair["score"], 0.5)
        self.assertEqual(pair["rightFaceId"], 1)
        dumped = str(env)
        self.assertNotIn("faceId", dumped)
        self.assertNotIn("faceRegion", dumped)
        self.assertNotIn("similarity", dumped)
        self.assertNotIn("firstFaceId", dumped)


class ResultViewTests(unittest.TestCase):
    def test_detect_groups_quality_and_reads_value(self):
        payload = {
            "api": "face/1",
            "ok": True,
            "status": "IX_OK",
            "statusCode": 0,
            "elapsedMs": None,
            "entitlement": {"recognition": True, "liveness": True},
            "result": {
                "message": "COMPLETED",
                "faces": [
                    {
                        "id": 0,
                        "box": {"x": 10, "y": 20, "width": 80, "height": 90},
                        "pose": {"yaw": 1.2, "pitch": -3, "roll": 0},
                        "landmarks": [{"x": 1, "y": 2}],
                        "traits": {
                            "ageYears": {"value": 32, "confidence": 0.8},
                            "gender": {"value": "FEMALE", "confidence": 0.9},
                            "faceQuality": {"value": "GOOD", "confidence": 0.7},
                            "blurLevel": {"value": "LOW", "confidence": 0.6},
                            "liveness2d": {"value": "REAL", "confidence": 0.99},
                        },
                    }
                ],
            },
            "fault": None,
        }
        summary, rows, _raw = result_view.format_detect(payload)
        self.assertIn("1 face", summary)
        labels = [row[0] for row in rows]
        self.assertIn("Quality", labels)
        self.assertIn("faceQuality", labels)
        self.assertIn("blurLevel", labels)
        quality = next(row for row in rows if row[0] == "faceQuality")
        self.assertEqual(quality[1], "GOOD")
        self.assertEqual(quality[2], "0.7")
        region = next(row for row in rows if row[0].endswith("Region"))
        self.assertIn("10", region[1])

    def test_deepfake_reads_engine_value(self):
        self.assertEqual(result_view.deepfake_kind({"value": True, "confidence": 0.91}), "fake")
        self.assertEqual(result_view.deepfake_kind({"value": False, "confidence": 0.88}), "real")
        self.assertEqual(result_view.deepfake_kind({"value": "FAKE", "confidence": 0.7}), "fake")
        self.assertEqual(result_view.deepfake_kind({"value": "REAL", "confidence": 0.7}), "real")
        fake, _rows, _raw = result_view.format_detect(
            {
                "api": "face/1",
                "ok": True,
                "status": "IX_OK",
                "statusCode": 0,
                "result": {
                    "faces": [
                        {"traits": {"deepfake": {"value": True, "confidence": 0.91, "info": "swap"}}}
                    ]
                },
                "fault": None,
            },
            title="Deepfake",
        )
        self.assertIn("Deepfake: 1", fake)
        self.assertIn("0.910000", fake)
        real, _rows, _raw = result_view.format_detect(
            {
                "api": "face/1",
                "ok": True,
                "status": "IX_OK",
                "statusCode": 0,
                "result": {"faces": [{"traits": {"deepfake": {"value": False, "confidence": 0.2}}}]},
                "fault": None,
            },
            title="Deepfake",
        )
        self.assertIn("Deepfake: 0", real)
        self.assertIn("0.200000", real)

    def test_identify_joins_name_and_keeps_stable_index(self):
        payload = {
            "api": "face/1",
            "ok": True,
            "status": "IX_OK",
            "statusCode": 0,
            "result": {
                "detects": [{"imageId": 0, "status": 0, "faces": [{"id": 0}]}],
                "pairs": [
                    {
                        "leftFaceId": 0,
                        "rightFaceId": 0,
                        "leftImageId": 0,
                        "rightImageId": 12,
                        "score": 0.8123,
                    }
                ],
            },
            "fault": None,
        }
        summary, rows, _raw, best = result_view.format_identify(payload, {12: "Bea"})
        self.assertIn("FOUND", summary)
        self.assertIn("Bea", summary)
        self.assertIn("0.8123", summary)
        self.assertEqual(best, 12)
        self.assertEqual(rows[0][0], "Bea")
        self.assertEqual(rows[0][1], "12")

    def test_identify_no_match_and_errors(self):
        summary, rows, _raw, best = result_view.format_identify(
            ix_payload.wrap_process({"status": 0, "pairs": []}), {}
        )
        self.assertIn("NO MATCH", summary)
        self.assertEqual(rows, [])
        self.assertIsNone(best)
        summary, _rows, _raw, best = result_view.format_identify(
            ix_payload.wrap_process({"status": 2, "message": "NO_FACE"}), {}
        )
        self.assertIn("NO_FACE", summary)
        self.assertIsNone(best)
        summary, _rows, _raw, best = result_view.format_identify(
            ix_payload.wrap_process({"status": -1, "message": "gallery is empty"}), {}
        )
        self.assertIn("gallery is empty", summary)

    def test_match_and_liveness_readers(self):
        summary, rows, _raw = result_view.format_match(
            {
                "api": "face/1",
                "ok": True,
                "status": "IX_OK",
                "statusCode": 0,
                "result": {
                    "detects": [
                        {"imageId": 0, "status": 0, "faces": [{}]},
                        {"imageId": 1, "status": 2, "faces": []},
                    ],
                    "pairs": [
                        {
                            "leftFaceId": 0,
                            "rightFaceId": 1,
                            "leftImageId": 0,
                            "rightImageId": 1,
                            "score": 0.42,
                        }
                    ],
                },
                "fault": None,
            }
        )
        self.assertIn("NO FACE", summary)
        self.assertIn("0.42", rows[2][2])
        self.assertEqual(rows[0][1], "face found")
        self.assertEqual(rows[1][1], "no face")
        same, same_rows, _raw = result_view.format_match(
            {
                "api": "face/1",
                "ok": True,
                "status": "IX_OK",
                "statusCode": 0,
                "result": {
                    "detects": [
                        {"imageId": 0, "status": 0, "faces": [{}]},
                        {"imageId": 1, "status": 0, "faces": [{}]},
                    ],
                    "pairs": [
                        {
                            "leftFaceId": 0,
                            "rightFaceId": 0,
                            "leftImageId": 0,
                            "rightImageId": 1,
                            "score": 0.88,
                        }
                    ],
                },
                "fault": None,
            }
        )
        self.assertIn("SAME PERSON", same)
        self.assertIn("0.88", same)
        self.assertEqual(same_rows[2][2], "0.88")
        text, rows, _raw = result_view.format_liveness(
            {
                "api": "face/1",
                "ok": True,
                "status": "IX_OK",
                "statusCode": 0,
                "result": {
                    "faces": [
                        {
                            "box": {"x": 1, "y": 2, "width": 3, "height": 4},
                            "pose": {"yaw": 0, "pitch": 0, "roll": 1},
                            "traits": {"liveness2d": {"value": "REAL", "confidence": 0.91}},
                        }
                    ]
                },
                "fault": None,
            }
        )
        self.assertEqual(text, "")
        self.assertEqual(rows[0][:2], ["Liveness", "REAL"])
        self.assertEqual(rows[0][2], "0.910000")
        _directed, directed_rows, _raw = result_view.format_liveness(
            {
                "api": "face/1",
                "ok": True,
                "status": "IX_OK",
                "statusCode": 0,
                "result": {
                    "faces": [
                        {
                            "box": {"x": 1, "y": 2, "width": 3, "height": 4},
                            "traits": {"liveness2d": {"result": "fake", "liveness_score": 0.26}},
                        }
                    ]
                },
                "fault": None,
            }
        )
        self.assertEqual(directed_rows[0][:2], ["Liveness", "FAKE"])
        self.assertEqual(directed_rows[0][2], "0.260000")
        _zero, zero_rows, _raw = result_view.format_liveness(
            {
                "api": "face/1",
                "ok": True,
                "status": "IX_OK",
                "statusCode": 0,
                "result": {
                    "faces": [
                        {
                            "traits": {"liveness2d": {"result": "fake", "liveness_score": 0}},
                        }
                    ]
                },
                "fault": None,
            }
        )
        self.assertEqual(zero_rows[0][:2], ["Liveness", "FAKE"])
        self.assertEqual(zero_rows[0][2], "0.000000")

    def test_match_and_liveness_multiple_faces(self):
        summary, rows, _raw = result_view.format_match(
            {
                "api": "face/1",
                "ok": True,
                "status": "IX_OK",
                "statusCode": 0,
                "result": {
                    "detects": [
                        {"imageId": 0, "status": 0, "faces": [{}, {}]},
                        {"imageId": 1, "status": 0, "faces": [{}]},
                    ],
                    "pairs": [
                        {
                            "leftFaceId": 0,
                            "rightFaceId": 0,
                            "leftImageId": 0,
                            "rightImageId": 1,
                            "score": 0.88,
                        },
                        {
                            "leftFaceId": 1,
                            "rightFaceId": 0,
                            "leftImageId": 0,
                            "rightImageId": 1,
                            "score": 0.41,
                        },
                    ],
                },
                "fault": None,
            }
        )
        self.assertIn("SAME PERSON", summary)
        self.assertIn("0.88", summary)
        self.assertIn("Best of 2 pairs", summary)
        self.assertEqual(rows[2][2], "0.88")
        self.assertEqual(rows[3][2], "0.41")
        html = result_view.match_pairs_html(None, None, {
            "api": "face/1",
            "ok": True,
            "status": "IX_OK",
            "statusCode": 0,
            "result": {
                "detects": [
                    {"imageId": 0, "status": 0, "faces": [{}]},
                    {"imageId": 1, "status": 0, "faces": [{}]},
                ],
                "pairs": [
                    {
                        "leftFaceId": 0,
                        "rightFaceId": 0,
                        "leftImageId": 0,
                        "rightImageId": 1,
                        "score": 0.41,
                    }
                ],
            },
            "fault": None,
        })
        self.assertIn("DIFFERENT PEOPLE", html)
        mixed, mixed_rows, _raw = result_view.format_liveness(
            {
                "api": "face/1",
                "ok": True,
                "status": "IX_OK",
                "statusCode": 0,
                "result": {
                    "faces": [
                        {"traits": {"liveness2d": {"value": "REAL", "confidence": 0.91}}},
                        {"traits": {"liveness2d": {"result": "fake", "liveness_score": 0.26}}},
                    ]
                },
                "fault": None,
            }
        )
        self.assertEqual(mixed, "")
        self.assertEqual(mixed_rows[0][:2], ["Liveness", "REAL"])
        self.assertEqual(mixed_rows[1][:2], ["Liveness", "FAKE"])
        live_html = result_view.liveness_pairs_html(
            None,
            {
                "api": "face/1",
                "ok": True,
                "status": "IX_OK",
                "statusCode": 0,
                "result": {
                    "faces": [
                        {"traits": {"liveness2d": {"value": "REAL", "confidence": 0.91}}},
                        {"traits": {"liveness2d": {"result": "fake", "liveness_score": 0.26}}},
                    ]
                },
                "fault": None,
            },
        )
        self.assertIn("REAL", live_html)
        self.assertIn("FAKE", live_html)
        self.assertIn("ix-crop", live_html)
        self.assertIn("ix-live-table", live_html)
        self.assertIn("<th>Face</th>", live_html)
        self.assertNotIn("Face 1", live_html)
        self.assertNotIn("<h4>", live_html)

    def test_liveness_check_requires_both_engines_real(self):
        def doc(live: dict, fake: dict) -> dict:
            return {
                "api": "face/1",
                "ok": True,
                "status": "IX_OK",
                "statusCode": 0,
                "result": {
                    "faces": [
                        {
                            "box": {"x": 1, "y": 2, "width": 3, "height": 4},
                            "pose": {"yaw": 0, "pitch": 0, "roll": 0},
                            "traits": {"liveness2d": live, "deepfake": fake},
                        }
                    ]
                },
                "fault": None,
            }

        both, both_rows, raw = result_view.format_liveness(
            doc(
                {
                    "value": "REAL",
                    "confidence": 0.91,
                    "liveness_score": 0.91,
                    "attack_type_scores": {"none": 0.9},
                },
                {"value": False, "confidence": 0.88},
            )
        )
        self.assertEqual(both, "")
        self.assertEqual(both_rows[0], ["Liveness", "REAL", "0.910000"])
        self.assertEqual(both_rows[1], ["Deepfake", "REAL", "0.880000"])
        self.assertIn("liveness2d", raw)
        self.assertIn("deepfake", raw)
        self.assertIn("attack_type_scores", raw)
        _live_only, live_only_rows, _raw = result_view.format_liveness(
            doc({"value": "REAL", "confidence": 0.91, "liveness_score": 0.91}, {"value": True, "confidence": 0.72})
        )
        self.assertEqual(live_only_rows[0][:2], ["Liveness", "REAL"])
        self.assertEqual(live_only_rows[1][:2], ["Deepfake", "FAKE"])
        _df_only, df_only_rows, _raw = result_view.format_liveness(
            doc({"value": "fake", "confidence": 0.26, "liveness_score": 0.26}, {"value": False, "confidence": 0.88})
        )
        self.assertEqual(df_only_rows[0][:2], ["Liveness", "FAKE"])
        self.assertEqual(df_only_rows[1][:2], ["Deepfake", "REAL"])
        html = result_view.liveness_pairs_html(
            None,
            doc({"value": "REAL", "confidence": 0.91, "liveness_score": 0.91}, {"value": True, "confidence": 0.72}),
        )
        self.assertIn("FAKE", html)
        self.assertIn("Liveness", html)
        self.assertIn("Deepfake", html)
        mixed, mixed_rows, _raw = result_view.format_liveness(
            {
                "api": "face/1",
                "ok": True,
                "status": "IX_OK",
                "statusCode": 0,
                "result": {
                    "faces": [
                        {
                            "traits": {
                                "liveness2d": {"value": "REAL", "confidence": 0.91, "liveness_score": 0.91},
                                "deepfake": {"value": False, "confidence": 0.88},
                            }
                        },
                        {
                            "traits": {
                                "liveness2d": {"value": "fake", "liveness_score": 0.26},
                                "deepfake": {"value": False, "confidence": 0.80},
                            }
                        },
                    ]
                },
                "fault": None,
            }
        )
        self.assertEqual(mixed, "")
        self.assertEqual(mixed_rows[0][:2], ["Liveness", "REAL"])
        self.assertEqual(mixed_rows[1][:2], ["Deepfake", "REAL"])
        self.assertEqual(mixed_rows[2][:2], ["Liveness", "FAKE"])
        self.assertEqual(mixed_rows[3][:2], ["Deepfake", "REAL"])

    def test_enroll_reads_feature_index(self):
        summary, rows, _raw = result_view.format_enroll(
            {
                "api": "face/1",
                "ok": True,
                "status": "IX_OK",
                "statusCode": 0,
                "result": {
                    "features": [
                        {
                            "index": 5,
                            "features": [
                                {
                                    "box": {"x": 0, "y": 0, "width": 10, "height": 12},
                                    "size": 512,
                                }
                            ],
                        }
                    ]
                },
                "fault": None,
            },
            "Ada",
        )
        self.assertIn("ENROLLED", summary)
        self.assertIn("Ada", summary)
        self.assertIn("5", summary)
        self.assertEqual(rows[1][1], "5")
        self.assertEqual(rows[3][1], "512")


class SdkBindingContractTests(unittest.TestCase):
    """Lock liveness-only HTTP bindings without loading the native lib."""

    def _source(self, name: str) -> str:
        root = Path(__file__).resolve().parents[1]
        path = {
            "app.py": root / "server" / "app.py",
            "sdk.py": root / "sdk" / "__init__.py",
            "demo.py": root / "demo" / "app.py",
        }[name]
        return path.read_text(encoding="utf-8")

    def test_server_exposes_liveness_routes_only(self):
        src = self._source("app.py")
        self.assertIn('@app.post("/api/face/liveness")', src)
        self.assertIn('@app.post("/api/face/deepfake")', src)
        self.assertNotIn('@app.post("/api/face/analyze")', src)
        self.assertNotIn('@app.post("/api/face/search")', src)
        self.assertNotIn('@app.post("/api/face/enroll")', src)

    def test_deepfake_and_liveness_use_encoded_image(self):
        src = self._source("sdk.py")
        self.assertIn("def deepfake(image: str) -> str:", src)
        self.assertIn("def liveness(image: str) -> str:", src)
        self.assertIn("image_b = _fit_encoded_b64(image)", src)
        self.assertIn("FaceSDK_liveness_all(image_b, 0, out)", src)
        self.assertIn("def _liveness_each_face", src)

    def test_demo_calls_face_liveness(self):
        src = self._source("demo.py")
        start = src.index("def check_liveness")
        end = src.index("\ndef ", start + 1)
        body = src[start:end]
        self.assertIn("/api/face/liveness", body)
        self.assertNotIn("/api/face/deepfake", body)
        self.assertIn("need_liveness=True", body)



if __name__ == "__main__":
    unittest.main()
