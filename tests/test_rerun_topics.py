import unittest
from unittest.mock import patch

from tools.rerun_topics import (
    IMAGES_DIR,
    Selection,
    article_path,
    article_paths,
    publication_paths,
    superseded_image_paths,
)


class RerunPublicationTests(unittest.TestCase):
    def test_costs_only_publishes_only_the_english_article(self) -> None:
        topic = "What is AI?"

        paths = publication_paths([topic], Selection(costs=True), {})

        self.assertEqual(paths, (article_path(topic),))

    def test_agent_rerun_includes_articles_and_old_and_new_images(self) -> None:
        topic = "What is AI?"
        original_images = {topic: {"path": "/images/old.webp"}}
        current_images = {topic: {"path": "/images/new.webp"}}

        with patch("tools.rerun_topics.read_json_or_empty", return_value=current_images):
            paths = set(publication_paths([topic], Selection(images=True), original_images))

        self.assertEqual(
            paths,
            {
                *article_paths(topic),
                IMAGES_DIR / "old.webp",
                IMAGES_DIR / "new.webp",
            },
        )

    def test_only_replaced_images_are_marked_as_intentionally_removed(self) -> None:
        topic = "What is AI?"
        original_images = {topic: {"path": "/images/old.webp"}}
        current_images = {topic: {"path": "/images/new.webp"}}

        with (
            patch("tools.rerun_topics.read_json_or_empty", return_value=current_images),
            patch("pathlib.Path.exists", return_value=False),
        ):
            removed = superseded_image_paths([topic], Selection(images=True), original_images)

        self.assertEqual(removed, (IMAGES_DIR / "old.webp",))


if __name__ == "__main__":
    unittest.main()
