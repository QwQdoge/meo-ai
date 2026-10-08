import json
import sys
import types
import unittest
from unittest import mock

from meo.adapters.legacy_chat import LegacyChatInterfaceAdapter


class FakeSettings:
    def __init__(self):
        self.values = {
            "language-model": "local",
            "llm-settings": json.dumps({"local": {"model": "old"}}),
        }

    def get_string(self, key):
        return self.values[key]

    def set_string(self, key, value):
        self.values[key] = value


class FakeHandler:
    def __init__(self, settings, directory):
        self.settings = settings
        self.directory = directory

    def get_models_list(self):
        return [("tiny", "Tiny Model"), ("large", "Large Model")]


class FakeSkill:
    def __init__(self, name):
        self.name = name


class FakeSkillManager:
    def __init__(self):
        self.skills = {"diagnostics": FakeSkill("diagnostics"), "git": FakeSkill("git")}
        self.enabled = {"diagnostics": True, "git": False}

    def is_skill_enabled(self, name):
        return self.enabled[name]

    def set_skill_enabled(self, name, enabled):
        self.enabled[name] = enabled


class FakeController:
    def __init__(self):
        self.settings = FakeSettings()
        self.handlers = types.SimpleNamespace(directory="/tmp/handlers")
        self.newelle_settings = types.SimpleNamespace(language_model="local")
        self.skill_manager = FakeSkillManager()
        self.updated = 0

    def update_settings(self):
        self.updated += 1


class FakeInterface:
    def __init__(self):
        self.controller = FakeController()
        self.chat = 0

    def get_or_create_chat(self, _user_id):
        self.chat += 1
        return self.chat


class LegacyCatalogTests(unittest.TestCase):
    def constants_module(self):
        module = types.ModuleType("src.constants")
        module.AVAILABLE_LLMS = {
            "local": {"title": "Local Provider", "class": FakeHandler},
        }
        return module

    def test_structured_models_and_model_switch(self):
        adapter = LegacyChatInterfaceAdapter(FakeInterface())
        conversation = adapter.create_conversation()
        with mock.patch.dict(sys.modules, {"src.constants": self.constants_module()}):
            models = adapter.list_models()
            self.assertEqual([model.model_id for model in models], ["local:tiny", "local:large"])
            self.assertEqual(models[0].label, "Tiny Model")
            adapter.set_model(conversation, "local:large")
        settings = adapter.controller.settings
        self.assertEqual(settings.get_string("language-model"), "local")
        self.assertEqual(json.loads(settings.get_string("llm-settings"))["local"]["model"], "large")
        self.assertEqual(adapter.controller.updated, 1)

    def test_unknown_conversation_cannot_change_model(self):
        adapter = LegacyChatInterfaceAdapter(FakeInterface())
        with mock.patch.dict(sys.modules, {"src.constants": self.constants_module()}):
            with self.assertRaises(ValueError):
                adapter.set_model("meo:missing", "local:large")

    def test_skills_are_structured_and_toggleable(self):
        adapter = LegacyChatInterfaceAdapter(FakeInterface())
        skills = adapter.list_skills()
        self.assertEqual([skill.skill_id for skill in skills], ["diagnostics", "git"])
        self.assertTrue(skills[0].enabled)
        self.assertFalse(skills[1].enabled)
        adapter.set_skill_enabled("git", True)
        self.assertTrue(adapter.controller.skill_manager.enabled["git"])
        with self.assertRaises(ValueError):
            adapter.set_skill_enabled("missing", True)


if __name__ == "__main__":
    unittest.main()
