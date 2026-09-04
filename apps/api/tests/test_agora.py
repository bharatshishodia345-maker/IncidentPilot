from __future__ import annotations

import base64
import zlib

from app.services.agora import AgoraTokenService, AccessToken2, ServiceRtc, unpack_uint16, unpack_string


def test_agora_token_service_generates_valid_token_structure() -> None:
    app_id = "test_agora_app_id_999"
    app_cert = "test_agora_certificate_88888888888888888888"
    channel_name = "incident-channel-test"
    uid = "12345"

    token = AgoraTokenService.generate_rtc_token(
        app_id=app_id,
        app_certificate=app_cert,
        channel_name=channel_name,
        uid=uid,
        is_publisher=True,
        expire_seconds=3600,
    )

    # Must start with AccessToken2 version prefix '007'
    assert token.startswith("007")

    # Verify base64 and zlib decompression
    b64_part = token[3:]
    compressed = base64.b64decode(b64_part)
    decompressed = zlib.decompress(compressed)

    # Check decompressed structure
    assert len(decompressed) > 32  # Contains 32-byte HMAC signature + message
    message = decompressed[32:]

    # First part of message is app_id packed as uint16-length + string
    unpacked_app_id, rest = unpack_string(message)
    assert unpacked_app_id == app_id


def test_agora_publisher_vs_subscriber_token() -> None:
    app_id = "app_123"
    app_cert = "cert_456"

    pub_token = AgoraTokenService.generate_rtc_token(
        app_id=app_id,
        app_certificate=app_cert,
        channel_name="room-1",
        uid="100",
        is_publisher=True,
    )

    sub_token = AgoraTokenService.generate_rtc_token(
        app_id=app_id,
        app_certificate=app_cert,
        channel_name="room-1",
        uid="100",
        is_publisher=False,
    )

    assert pub_token != sub_token
    assert pub_token.startswith("007")
    assert sub_token.startswith("007")
