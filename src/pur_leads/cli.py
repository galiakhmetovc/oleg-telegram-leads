"""Command-line entrypoint for PUR Leads."""

from __future__ import annotations


def main() -> None:
    """Run the PUR Leads CLI.

    Full command groups are added in the developer workflow task. Keeping the
    entrypoint importable now lets packaging and smoke checks succeed.
    """
    print("PUR Leads")
