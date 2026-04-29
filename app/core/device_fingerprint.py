"""Compute SHA-256 device fingerprint hashes + IP subnet (pure logic).

Per .planning/phases/11-auth-core-modules-services-di/11-CONTEXT.md §111-119 (locked):
- cookie_hash: SHA-256 of cookie_value (hex, 64 chars).
- ua_hash:     SHA-256 of user_agent (hex, 64 chars).
- ip_subnet:   IPv4 -> /24 masked; IPv6 -> /64 masked (string form).
- device_id:   passed through as-is.
"""

from __future__ import annotations

import ipaddress

from app.core._hashing import _sha256_hex

_IPV4_PREFIX = 24
_IPV6_PREFIX = 64
assert _IPV4_PREFIX == 24, "IPv4 subnet prefix drift"
assert _IPV6_PREFIX == 64, "IPv6 subnet prefix drift"


def compute(
    *,
    cookie_value: str,
    user_agent: str,
    client_ip: str,
    device_id: str,
) -> dict[str, str]:
    """Return device fingerprint dict (cookie_hash, ua_hash, ip_subnet, device_id)."""
    return {
        "cookie_hash": _sha256_hex(cookie_value),
        "ua_hash": _sha256_hex(user_agent),
        "ip_subnet": _ip_subnet(client_ip),
        "device_id": device_id,
    }


def _ip_subnet(client_ip: str) -> str:
    """Mask IP to /24 (IPv4) or /64 (IPv6) network string."""
    addr = ipaddress.ip_address(client_ip)
    if isinstance(addr, ipaddress.IPv4Address):
        return str(ipaddress.ip_network(f"{client_ip}/{_IPV4_PREFIX}", strict=False))
    return str(ipaddress.ip_network(f"{client_ip}/{_IPV6_PREFIX}", strict=False))
