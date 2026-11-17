import sqlite3
import csv
import tempfile
import unittest
from pathlib import Path

from backend.import_youtube_playlist import CSV_COLUMNS, classify_video_title, reclassify_existing
from backend.persist_classification import ensure_classification_columns, store_title_classification
from backend.title_classifier import HuntTitle, classify_hunt_title


class ClassifyHuntTitleTests(unittest.TestCase):
    def test_classifies_supported_group_sizes(self):
        expected = {2: ("Duo", 2), 3: ("Trio", 3), 4: ("Team Hunt (PT)", 4), 5: ("Team Hunt (PT)", 5)}
        for count, expected_result in expected.items():
            with self.subTest(count=count):
                result = classify_hunt_title(f"MS hunting x{count}")
                self.assertEqual((result.hunt_type, result.players_count), expected_result)

    def test_ignores_loot_multiplier(self):
        self.assertIsNone(classify_hunt_title("MS 2x loot at example cave").hunt_type)

    def test_user_confirmed_manual_solo_overrides_are_preserved(self):
        self.assertEqual(classify_video_title(
            "Y5aTqA8NC7U", "MS 1335 Hunt Cobra Bastion"
        ), HuntTitle("Solo", 1, False))

    def test_duo_means_two_player_team(self):
        result = classify_hunt_title("MS Hunt Duo Asura Mirror")
        self.assertEqual(result.hunt_type, "Duo")
        self.assertEqual(result.players_count, 2)
        self.assertFalse(result.needs_review)

    def test_duo_with_x2_is_not_a_conflict(self):
        result = classify_hunt_title("MS Duo x2 hunt")
        self.assertEqual(result.players_count, 2)
        self.assertFalse(result.needs_review)

    def test_duo_with_different_explicit_size_is_reviewable(self):
        result = classify_hunt_title("Duo x3 hunt")
        self.assertEqual(result.hunt_type, "Trio")
        self.assertEqual(result.players_count, 3)
        self.assertTrue(result.needs_review)

    def test_duo_with_solo_is_reviewable_and_team_wins(self):
        result = classify_hunt_title("Solo Duo MS hunt")
        self.assertEqual(result.hunt_type, "Duo")
        self.assertEqual(result.players_count, 2)
        self.assertTrue(result.needs_review)

    def test_ignores_markers_inside_larger_words(self):
        for title in ("prefixx2", "x2fast", "soloist x3man"):
            with self.subTest(title=title):
                result = classify_hunt_title(title)
                self.assertIsNone(result.hunt_type)

    def test_solo_is_classified_with_one_player(self):
        self.assertEqual(classify_hunt_title("Solo MS hunt"), HuntTitle("Solo", 1, False))

    def test_team_wins_over_solo_and_marks_for_review(self):
        result = classify_hunt_title("Solo MS x4 hunt")
        self.assertEqual(result.hunt_type, "Team Hunt (PT)")
        self.assertEqual(result.players_count, 4)
        self.assertTrue(result.needs_review)
        self.assertIn("solo", result.review_reason)

    def test_conflicting_team_sizes_use_first_and_mark_for_review(self):
        result = classify_hunt_title("x3 or x4 MS hunt")
        self.assertEqual(result.hunt_type, "Team Hunt (PT)")
        self.assertEqual(result.players_count, 4)
        self.assertTrue(result.needs_review)


class PersistClassificationTests(unittest.TestCase):
    def test_adds_columns_and_stores_reviewable_conflict(self):
        connection = sqlite3.connect(":memory:")
        connection.execute("CREATE TABLE videos (video_id TEXT PRIMARY KEY, title TEXT)")
        connection.execute("INSERT INTO videos(video_id, title) VALUES ('abc', 'Solo MS x2')")
        ensure_classification_columns(connection)
        store_title_classification(connection, "abc", "Solo MS x2")
        row = connection.execute(
            "SELECT hunt_type, players_count, needs_review, review_reason FROM videos WHERE video_id='abc'"
        ).fetchone()
        self.assertEqual(row[0:3], ("Duo", 2, 1))
        self.assertIn("solo", row[3])


class ReclassifyExistingTests(unittest.TestCase):
    def test_reclassifies_csv_and_database_without_api(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            csv_path = directory / "videos.csv"
            db_path = directory / "videos.db"
            row = {column: "" for column in CSV_COLUMNS}
            row.update(video_id="vid1", title="MS Hunt Duo Asura Mirror", position="1",
                       video_url="https://www.youtube.com/watch?v=vid1")
            with csv_path.open("w", newline="", encoding="utf-8-sig") as file:
                writer = csv.DictWriter(file, fieldnames=CSV_COLUMNS)
                writer.writeheader()
                writer.writerow(row)
            connection = sqlite3.connect(db_path)
            try:
                connection.execute("""CREATE TABLE videos (
                    video_id TEXT PRIMARY KEY, hunt_type TEXT, players_count INTEGER,
                    needs_review INTEGER, review_reason TEXT
                )""")
                connection.execute("INSERT INTO videos(video_id) VALUES ('vid1')")
                connection.commit()
            finally:
                connection.close()

            rows = reclassify_existing(csv_path, db_path)

            self.assertEqual(rows[0]["hunt_type"], "Duo")
            self.assertEqual(rows[0]["players_count"], 2)
            connection = sqlite3.connect(db_path)
            try:
                stored = connection.execute(
                    "SELECT hunt_type, players_count FROM videos WHERE video_id='vid1'"
                ).fetchone()
            finally:
                connection.close()
            self.assertEqual(stored, ("Duo", 2))


if __name__ == "__main__":
    unittest.main()
