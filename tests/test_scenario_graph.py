"""Transfer evidence must survive native operand and assignment boundaries."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import scenario_graph
import scenario_membership


class NoTextKit:
    TEXT_OPCODE = b"\x02\x0b\x00\x0a"

    @staticmethod
    def read_text_records_structured(*args):
        return []


def scenario(code):
    return b"VE\0\0" + struct.pack("<III", len(code), 0, 0) + code


def number(value):
    return b"\x09\x04" + struct.pack("<f", value) + b"\x02"


class ScenarioGraphTests(unittest.TestCase):
    def test_variable_index_preserves_following_flag_write(self):
        for index in (2, 5, 9, 10, 0x36):
            with self.subTest(index=index):
                expression = b"\x06" + bytes((index,)) + number(1)[:-1] + b"\x2a\x02"
                branch = b"\x02\x08\x61" + expression + b"\x05\x02@A\x02"
                write = b"\x02\x08\x1e" + number(3) + number(6)
                payload = scenario(branch + write)
                _, _, sites, _ = scenario_graph.scan_sites(payload, NoTextKit)
                self.assertEqual([site["command_id"] for site in sites], [0x61, 0x1E])
                self.assertEqual(sites[0]["operands"][0]["raw_hex"], expression.hex())
                self.assertEqual(sites[0]["operands"][1]["value"], "@A")
                self.assertEqual([arg["value"] for arg in sites[1]["operands"]], [3, 6])

    def test_assignment_terminator_also_frames_following_scenario_load(self):
        assignment = b"\x07\x36\x36\x13" + number(0)[:-1] + b"\x22\x02"
        load = b"\x08\x1f\x0a\x09\x00" + b"420020010" + b"\x02"
        payload = scenario(assignment + load + b"\x02\x08\x01")
        start, _, sites, _ = scenario_graph.scan_sites(payload, NoTextKit)
        self.assertEqual([site["command_id"] for site in sites], [0x1F, 0x01])
        self.assertEqual(sites[0]["framing_payload_offset"], 16 + len(assignment) - 1)
        self.assertEqual(sites[0]["operands"][0]["value"], "420020010")
        self.assertEqual(scenario_graph.frame_census(payload, start, sites, NoTextKit)["unmatched"], [])

    def test_unconditional_label_and_local_copy_preserve_following_command(self):
        jump = b"\x02\x08\x63\x05\x04@END\x02"
        copy = b"\x02\x08\x86" + number(1) + number(0)
        payload = scenario(jump + copy + b"\x02\x08\x01")
        start, _, sites, _ = scenario_graph.scan_sites(payload, NoTextKit)
        self.assertEqual([site["command_id"] for site in sites], [0x63, 0x86, 0x01])
        self.assertEqual(sites[0]["operands"][0]["value"], "@END")
        self.assertEqual([arg["value"] for arg in sites[1]["operands"]], [1, 0])
        self.assertEqual(scenario_graph.frame_census(payload, start, sites, NoTextKit)["unmatched"], [])


class ScenarioMembershipTests(unittest.TestCase):
    @staticmethod
    def edge(source, target, kind="load_scenario", resolution="resolved_literal"):
        return {"source_script": source, "target_script": target,
                "kind": kind, "resolution": resolution}

    def test_deferred_and_shared_ownership_does_not_promote_other_stories_to_base(self):
        nodes = ["base", "ad", "extra", "terminal", "ad_extra", "slot", "inactive"]
        edges = [self.edge("base", "terminal"), self.edge("ad", "terminal"),
                 self.edge("extra", "terminal"), self.edge("ad", "ad_extra"),
                 self.edge("extra", "ad_extra"),
                 self.edge("base", "slot", kind="register_event_scenario"),
                 self.edge("slot", "base")]
        rows = scenario_membership.ownership(nodes, edges, {
            "base_game": ["base"], "anotherdays": ["ad"], "ikuno_story": ["extra"]})
        self.assertEqual(rows["terminal"]["status"], "shared")
        self.assertEqual(rows["slot"]["status"], "base_game")
        self.assertEqual(rows["ad_extra"]["status"], "anotherdays")
        self.assertEqual(rows["ad_extra"]["story_domains"], ["anotherdays", "ikuno_story"])
        self.assertEqual(rows["extra"]["status"], "other")
        self.assertTrue(rows["inactive"]["inactive_normal_story_program"])
        self.assertFalse(rows["slot"]["route_feasibility_proved"])

    def test_computed_load_prevents_a_closed_ownership_claim(self):
        edges = [self.edge("base", None, resolution="dynamic_numeric_expression")]
        with self.assertRaisesRegex(ValueError, "Dynamic scenario ingress"):
            scenario_membership.closure(["base"], edges, ["base"])

    def test_dynamic_global_index_or_month_copy_cannot_disappear_from_calendar_proof(self):
        literal_zero = {"status": "literal_number", "value": 0.0}
        effects = [
            {"source_script": "base", "kind": "write_global_flag",
             "operands": [{"status": "dynamic_numeric_expression"}, literal_zero]},
            {"source_script": "base", "kind": "write_global_flag_from_local",
             "operands": [literal_zero, literal_zero]},
        ]
        for effect in effects:
            with self.subTest(kind=effect["kind"]), self.assertRaises(ValueError):
                scenario_membership.month_writes({"state_effects": [effect]}, {"base"})


if __name__ == "__main__":
    unittest.main()
