import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe import validate_envelope, validate_api, verdict


class ProbeTest(unittest.TestCase):
    def envelope(self):
        return {"resolvedUrl": "https://in.bookmyshow.com/cinemas/hyderabad/allu-cinemas-kokapet/buytickets/ALUC/20261117",
                "venue": "ALUC", "selectedDate": "2026-11-17", "blocked": False, "empty": False,
                "shows": [{"movieId": "ET1", "title": "A Film", "language": "Telugu", "format": "DOLBY CINEMA 3D",
                           "time": "11:00 AM", "availability": "AVAILABLE", "sessionId": "123"}]}

    def test_verified_records_preserve_associations(self):
        result = validate_envelope("2026-11-17", self.envelope())
        self.assertEqual("SUCCESS", result["kind"])
        self.assertEqual("DOLBY_CINEMA", result["shows"][0]["format"])
        self.assertEqual(660, result["shows"][0]["startMinute"])

    def test_redirect_or_retained_url_is_not_date_proof(self):
        for field, value in (("selectedDate", ""), ("selectedDate", "2026-11-16"), ("venue", "OTHER"),
                             ("resolvedUrl", "https://evil.example")):
            envelope = self.envelope(); envelope[field] = value
            self.assertEqual("UNSUPPORTED", validate_envelope("2026-11-17", envelope)["kind"])

    def test_explicit_empty_and_blocked(self):
        envelope = self.envelope(); envelope["shows"] = []
        self.assertEqual("UNSUPPORTED", validate_envelope("2026-11-17", envelope)["kind"])
        envelope["empty"] = True
        self.assertEqual("EMPTY", validate_envelope("2026-11-17", envelope)["kind"])
        envelope["blocked"] = True
        self.assertEqual("BLOCKED", validate_envelope("2026-11-17", envelope)["kind"])

    def test_unknown_and_sold_out_never_satisfy_gate(self):
        for status in ("UNKNOWN", "SOLD_OUT", "unexpected"):
            envelope = self.envelope(); envelope["shows"][0]["availability"] = status
            sample = validate_envelope("2026-11-17", envelope) | {"round": 1}
            self.assertFalse(verdict([sample], ["2026-11-17"], 1))

    def test_every_round_and_date_required(self):
        sample = validate_envelope("2026-11-17", self.envelope()) | {"round": 1}
        self.assertFalse(verdict([sample], ["2026-11-17"], 2))
        second = copy.deepcopy(sample); second["round"] = 2
        self.assertTrue(verdict([sample, second], ["2026-11-17"], 2))
        self.assertFalse(verdict([sample, second], ["2026-11-17", "2026-11-18"], 2))

    def test_midnight_and_invalid_times(self):
        for time, minute in (("12:00AM", 0), ("12:00 PM", 720), ("9:45\u00a0PM", 1305)):
            envelope = self.envelope(); envelope["shows"][0]["time"] = time
            self.assertEqual(minute, validate_envelope("2026-11-17", envelope)["shows"][0]["startMinute"])
        for time in ("00:00 PM", "25:90", "some time"):
            envelope = self.envelope(); envelope["shows"][0]["time"] = time
            self.assertEqual("UNSUPPORTED", validate_envelope("2026-11-17", envelope)["kind"])

    def test_arbitrary_fields_are_not_exported(self):
        envelope = self.envelope(); envelope["cookies"] = "must-not-export"
        envelope["shows"][0]["account"] = "must-not-export"
        self.assertNotIn("must-not-export", str(validate_envelope("2026-11-17", envelope)))

    def test_api_response_requires_its_own_date_and_venue(self):
        details = {"Date": "20261117", "Venues": {"VenueCode": "ALUC", "VenueName": "ALLU Cinemas: Kokapet", "isVenueDown": False},
                   "Event": [{"EventTitle": "A Film", "ChildEvents": [{"EventCode": "ET1", "EventLanguage": "Telugu", "EventDimension": "3D",
                   "ShowTimes": [{"ShowDateCode": "20261117", "ShowDateTime": "202611171100", "ShowTime": "11:00 AM", "Attributes": "DOLBY CINEMA", "AvailStatus": "3", "SessionId": "123"}]}]}]}
        payload = {"ShowDetails": [details]}
        url = self.envelope()["resolvedUrl"]
        result = validate_api("2026-11-17", payload, url)
        self.assertEqual("SUCCESS", result["kind"])
        self.assertEqual("DOLBY_CINEMA", result["shows"][0]["format"])
        self.assertEqual("UNSUPPORTED", validate_api("2026-11-18", payload, url)["kind"])
        details["Venues"]["VenueCode"] = "OTHER"
        self.assertEqual("UNSUPPORTED", validate_api("2026-11-17", payload, url)["kind"])

    def test_api_does_not_infer_empty_from_missing_data(self):
        self.assertEqual("UNSUPPORTED", validate_api("2026-11-17", {"ShowDetails": []}, self.envelope()["resolvedUrl"])["kind"])


if __name__ == "__main__":
    unittest.main()
