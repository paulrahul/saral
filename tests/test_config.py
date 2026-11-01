import json
import tempfile
import unittest
from pathlib import Path

from llm.configuration import MODEL_COMPONENTS, load_model_config


def config_document() -> dict:
    return {
        "version": 1,
        "models": {
            component: {f"{component} model": f"provider/{component}"}
            for component in MODEL_COMPONENTS
        },
        "alternatives": {},
    }


class ModelConfigTests(unittest.TestCase):
    def write_config(self, document: object) -> Path:
        temporary = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        with temporary:
            json.dump(document, temporary)
        self.addCleanup(Path(temporary.name).unlink, missing_ok=True)
        return Path(temporary.name)

    def test_loads_every_component(self) -> None:
        loaded = load_model_config(self.write_config(config_document()))
        self.assertEqual(tuple(loaded), MODEL_COMPONENTS)
        self.assertEqual(loaded["translator"], {"translator model": "provider/translator"})

    def test_rejects_a_missing_component(self) -> None:
        document = config_document()
        del document["models"]["translator"]
        with self.assertRaisesRegex(ValueError, "translator"):
            load_model_config(self.write_config(document))

    def test_rejects_an_empty_model_mapping(self) -> None:
        document = config_document()
        document["models"]["image_generator"] = {}
        with self.assertRaisesRegex(ValueError, "image_generator"):
            load_model_config(self.write_config(document))

    def test_rejects_invalid_json(self) -> None:
        temporary = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        with temporary:
            temporary.write("{")
        self.addCleanup(Path(temporary.name).unlink, missing_ok=True)
        with self.assertRaisesRegex(ValueError, "line 1"):
            load_model_config(Path(temporary.name))

    def test_validates_but_does_not_activate_alternatives(self) -> None:
        document = config_document()
        document["alternatives"] = {
            "image_generator": {"Alternative image model": "provider/alternative-image"}
        }
        loaded = load_model_config(self.write_config(document))
        self.assertEqual(
            loaded["image_generator"],
            {"image_generator model": "provider/image_generator"},
        )

    def test_rejects_alternatives_for_unknown_components(self) -> None:
        document = config_document()
        document["alternatives"] = {"unknown_generator": {"Model": "provider/model"}}
        with self.assertRaisesRegex(ValueError, "unknown_generator"):
            load_model_config(self.write_config(document))


if __name__ == "__main__":
    unittest.main()
