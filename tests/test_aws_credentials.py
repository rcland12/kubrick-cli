"""Tests for parsing AWS credentials in .env / export form."""

import os
from datetime import datetime, timedelta, timezone

from kubrick_cli import aws_credentials as aws

BLOCK = """
# from the credentials portal
AWS_ACCESS_KEY_ID=AKIAEXAMPLE
AWS_SECRET_ACCESS_KEY="wJalr/K7MDENG+bPxRfiCYEXAMPLEKEY"
AWS_SESSION_TOKEN='FAKE-session-token-for-tests=='
AWS_TOKEN_EXPIRATION=2026-10-13T09:18:04Z
SOMETHING_ELSE=ignored
"""


def test_parses_plain_quoted_and_comment_lines():
    values = aws.parse_env_text(BLOCK)
    assert values["AWS_ACCESS_KEY_ID"] == "AKIAEXAMPLE"
    assert values["AWS_SECRET_ACCESS_KEY"] == "wJalr/K7MDENG+bPxRfiCYEXAMPLEKEY"
    assert values["AWS_SESSION_TOKEN"].endswith("==")
    assert "SOMETHING_ELSE" not in values
    assert aws.is_usable(values)


def test_parses_export_lines_and_one_line_pastes():
    exported = "export AWS_ACCESS_KEY_ID=A1\nexport AWS_SECRET_ACCESS_KEY=S1"
    assert aws.parse_env_text(exported) == {
        "AWS_ACCESS_KEY_ID": "A1",
        "AWS_SECRET_ACCESS_KEY": "S1",
    }
    one_line = (
        "export AWS_ACCESS_KEY_ID=A2 export AWS_SECRET_ACCESS_KEY=S2; "
        "export AWS_REGION=us-gov-west-1"
    )
    values = aws.parse_env_text(one_line)
    assert values["AWS_SECRET_ACCESS_KEY"] == "S2"
    assert aws.region_of(values) == "us-gov-west-1"
    windows = "set AWS_ACCESS_KEY_ID=A3\r\nset AWS_SECRET_ACCESS_KEY=S3\r\n"
    assert aws.parse_env_text(windows)["AWS_ACCESS_KEY_ID"] == "A3"


def test_bearer_token_alone_is_usable():
    assert aws.is_usable({"AWS_BEARER_TOKEN_BEDROCK": "bedrock-api-key-xyz"})
    assert not aws.is_usable({"AWS_ACCESS_KEY_ID": "only-half"})


def test_expiry():
    soon = (datetime.now(timezone.utc) + timedelta(hours=2, minutes=5)).isoformat()
    assert aws.describe_expiry({"AWS_TOKEN_EXPIRATION": soon}).startswith(
        "expires in 2h"
    )
    past = {"AWS_CREDENTIAL_EXPIRATION": "2020-01-01T00:00:00Z"}
    assert aws.seconds_left(past) < 0 and "ago" in aws.describe_expiry(past)
    assert aws.describe_expiry({"AWS_ACCESS_KEY_ID": "x"}) is None


def test_file_round_trip_is_private(tmp_path):
    path = tmp_path / "creds.env"
    aws.write_env_file(str(path), aws.parse_env_text(BLOCK))
    assert oct(os.stat(path).st_mode & 0o777) == "0o600"
    assert aws.load_env_file(str(path))["AWS_ACCESS_KEY_ID"] == "AKIAEXAMPLE"
    assert aws.load_env_file(str(tmp_path / "missing")) == {}


def test_json_round_trip():
    values = aws.parse_env_text(BLOCK)
    assert aws.from_json(aws.to_json(values)) == values
    assert (
        aws.from_json("AWS_ACCESS_KEY_ID=Z\nAWS_SECRET_ACCESS_KEY=Y")[
            "AWS_ACCESS_KEY_ID"
        ]
        == "Z"
    )
