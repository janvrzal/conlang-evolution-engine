"""Větev B: v roce 1300 západ dobude i východ (Pelna s hlavním městem, Sorrow, Mirost, Ulm)."""

import sys

import record2

base_spec = record2.spec


def spec() -> dict:
    data = base_spec()
    for event in data["events"]:
        if event["kind"] == "annexation":
            event["regions"] = event["regions"] + ["pelna", "sorrow", "mirost", "ulm"]
    data["events"] = [e for e in data["events"] if not (e["kind"] == "collapse" and e["state"] == "vychod")]
    return data


record2.spec = spec

if __name__ == "__main__":
    record2.main(sys.argv[1])
