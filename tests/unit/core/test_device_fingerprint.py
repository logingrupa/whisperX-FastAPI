"""Unit tests for app.core.device_fingerprint.

Per .planning/phases/11-auth-core-modules-services-di/11-02-PLAN.md (Task 2 §F).
Covers ANTI-03 device fingerprint hashing (SHA-256 cookie/UA + IP subnet masking).
"""

from __future__ import annotations

import pytest

from app.core import device_fingerprint


@pytest.mark.unit
class TestDeviceFingerprint:
    def test_compute_returns_all_four_keys(self) -> None:
        fp = device_fingerprint.compute(
            cookie_value="cookie-x",
            user_agent="Mozilla/5.0",
            client_ip="10.1.2.3",
            device_id="abc-123",
        )
        assert set(fp.keys()) == {"cookie_hash", "ua_hash", "ip_subnet", "device_id"}

    def test_hashes_are_64_hex_chars(self) -> None:
        fp = device_fingerprint.compute(
            cookie_value="c", user_agent="u", client_ip="10.1.2.3", device_id="d",
        )
        assert len(fp["cookie_hash"]) == 64
        assert len(fp["ua_hash"]) == 64

    def test_ipv4_subnet_is_24(self) -> None:
        fp = device_fingerprint.compute(
            cookie_value="c", user_agent="u",
            client_ip="192.168.1.42", device_id="d",
        )
        assert fp["ip_subnet"] == "192.168.1.0/24"

    def test_ipv6_subnet_is_64(self) -> None:
        fp = device_fingerprint.compute(
            cookie_value="c", user_agent="u",
            client_ip="2001:db8::1", device_id="d",
        )
        assert fp["ip_subnet"].endswith("/64")
