from __future__ import annotations

import json
import unittest

from meo.adapters.account_multimodal import account_model_supports_vision, context_payload
from meo.system.account_ai import DbusNextAccountAiClient


class AccountAiMultimodalTest(unittest.TestCase):
    def test_inference_arguments_include_images_in_bound_payload(self):
        image = "data:image/png;base64,QUJDRA=="
        arguments = DbusNextAccountAiClient.inference_arguments(
            connection_id="connection-one",
            model="vision-model",
            purpose="meo_ai_conversation",
            user_prompt="Describe the image",
            data_categories=("user_prompt", "user_images"),
            input_images=(image,),
        )
        self.assertEqual(arguments["inputImages"], [image])
        self.assertEqual(arguments["dataCategories"], ["user_prompt", "user_images"])

    def test_images_require_explicit_data_category(self):
        with self.assertRaisesRegex(ValueError, "user_images"):
            DbusNextAccountAiClient.inference_arguments(
                connection_id="connection-one",
                model="vision-model",
                purpose="meo_ai_conversation",
                user_prompt="Describe the image",
                input_images=("data:image/png;base64,QUJDRA==",),
            )

    def test_account_vision_capability_requires_exact_explicit_model(self):
        connections = [
            {
                "id": "connection-one",
                "defaultModel": "vision-model",
                "visionModels": ["vision-model", "other-vision"],
            },
            {
                "id": "legacy-connection",
                "defaultModel": "legacy-model",
            },
        ]
        self.assertTrue(
            account_model_supports_vision(connections, "connection-one:vision-model")
        )
        self.assertFalse(
            account_model_supports_vision(connections, "connection-one:vision-model-mini")
        )
        self.assertFalse(
            account_model_supports_vision(connections, "legacy-connection:legacy-model")
        )
        self.assertFalse(account_model_supports_vision(connections, "malformed"))

    def test_current_images_are_extracted_and_history_base64_is_not_replayed(self):
        current_image = "data:image/png;base64,Q1VSUkVOVA=="
        old_image = "data:image/png;base64,T0xESU1BR0U="
        prompt = (
            "Attached image: current.png\n"
            "```image\n"
            f"{current_image}\n"
            "```\n\n"
            "What is shown here?"
        )
        history = [
            {
                "User": "User",
                "Message": (
                    "Older attachment\n"
                    "```image\n"
                    f"{old_image}\n"
                    "```\n\n"
                    "Earlier question"
                ),
            }
        ]

        encoded, images = context_payload(prompt, history)
        payload = json.loads(encoded)

        self.assertEqual(images, (current_image,))
        self.assertNotIn(current_image, payload["current_user_prompt"])
        self.assertNotIn(old_image, payload["conversation_history"][0]["content"])
        self.assertIn("[Image attachment]", payload["current_user_prompt"])
        self.assertIn("[Image attachment]", payload["conversation_history"][0]["content"])
        self.assertIn("What is shown here?", payload["current_user_prompt"])

    def test_image_count_is_bounded_without_newelle_dependencies(self):
        image = "data:image/png;base64,QQ=="
        prompt = "\n".join(f"```image\n{image}\n```" for _ in range(9))
        with self.assertRaisesRegex(ValueError, "At most 8 images"):
            context_payload(prompt, [])


if __name__ == "__main__":
    unittest.main()
