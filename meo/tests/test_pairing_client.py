import unittest
from unittest.mock import patch
from meo.device.pairing_client import PairingClient, PairingClientConfig

class PairingClientTests(unittest.IsolatedAsyncioTestCase):
    def test_enrollment_and_relay_have_distinct_owners(self):
        client=PairingClient(PairingClientConfig(cloud_url="https://ai.meoarch.org",device_id="fixture-device",display_name="Fixture"))
        self.assertEqual(client.base_url,"https://api.meoarch.org")
        self.assertEqual(client.config.cloud_url,"https://ai.meoarch.org")

    def test_api_credentials_and_paths_are_rejected(self):
        for url in ["https://user:password@example.invalid","https://example.invalid/path","http://example.invalid"]:
            with self.assertRaises(ValueError):
                PairingClient(PairingClientConfig(cloud_url="https://ai.meoarch.org",api_url=url,device_id="fixture-device",display_name="Fixture"))

    async def test_pairing_uses_versioned_meo_api_without_exposing_the_secret(self):
        client=PairingClient(PairingClientConfig(cloud_url="https://ai.meoarch.org",device_id="fixture-device",display_name="Fixture"))
        calls=[]
        def post(path,body):
            calls.append((path,body))
            if path.endswith('/start'):
                return {"user_code":"ABCD2345","pairing_secret":"fixture-secret","verification_uri_complete":"https://account.meoarch.org/connect-device?code=ABCD2345"}
            return {"state":"approved","device_token":"fixture-device-token"}
        client._post=post
        with patch('webbrowser.open') as browser,patch('builtins.print') as output:
            self.assertEqual(await client.enroll(),"fixture-device-token")
            browser.assert_called_once()
            self.assertNotIn("fixture-secret",str(output.call_args_list))
        self.assertEqual([p for p,_ in calls],["/v1/ai/device-enrollments/start","/v1/ai/device-enrollments/poll"])
        self.assertEqual(calls[1][1],{"pairing_secret":"fixture-secret"})
