"""Unit tests for the Bedrock Converse provider (fake client, no boto3 needed)."""

import base64
import json

import pytest

from kubrick_cli.messages import (
    MessageDone,
    TextDelta,
    ThinkingDelta,
    ToolCallEvent,
    ToolSpec,
)
from kubrick_cli.providers.base import ProviderError
from kubrick_cli.providers.bedrock_provider import BedrockProvider

MODEL = "us.anthropic.test-model-v1:0"

READ_TOOL = ToolSpec(
    name="read_file",
    description="Read a file",
    parameters={
        "type": "object",
        "properties": {"file_path": {"type": "string"}},
        "required": ["file_path"],
    },
)


class FakeClientError(Exception):
    """Mimics botocore.exceptions.ClientError's ``response`` attribute."""

    def __init__(self, code, message="boom"):
        super().__init__(f"{code}: {message}")
        self.response = {"Error": {"Code": code, "Message": message}}


class NoCredentialsError(Exception):
    """Same class name as botocore's, which is all the provider inspects."""


class FakeClient:
    """Records converse_stream requests and replays scripted outcomes."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def converse_stream(self, **request):
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return {"stream": iter(outcome)}


def text_stream(text="Hello", stop="end_turn"):
    return [
        {"messageStart": {"role": "assistant"}},
        {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": text}}},
        {"contentBlockStop": {"contentBlockIndex": 0}},
        {"messageStop": {"stopReason": stop}},
        {"metadata": {"usage": {"inputTokens": 10, "outputTokens": 3}}},
    ]


def make_provider(*outcomes):
    provider = BedrockProvider(
        model=MODEL, region="us-east-1", client=FakeClient(*outcomes)
    )
    provider._sleep = lambda seconds: None
    return provider


def run(provider, messages, tools=None, options=None):
    return list(provider.stream_chat(messages, tools=tools, options=options))


class TestRequestConversion:
    def test_system_tools_and_inference_config(self):
        provider = make_provider(text_stream())
        run(
            provider,
            [
                {"role": "system", "content": "You are Kubrick."},
                {"role": "user", "content": "hi"},
            ],
            tools=[READ_TOOL],
            options={"max_tokens": 512, "temperature": 0.2},
        )
        request = provider.client.requests[0]
        assert request["modelId"] == MODEL
        assert request["system"] == [{"text": "You are Kubrick."}]
        assert request["messages"] == [{"role": "user", "content": [{"text": "hi"}]}]
        spec = request["toolConfig"]["tools"][0]["toolSpec"]
        assert spec["name"] == "read_file"
        assert spec["inputSchema"]["json"]["required"] == ["file_path"]
        assert request["inferenceConfig"] == {"maxTokens": 512, "temperature": 0.2}

    def test_tool_calls_and_grouped_results(self):
        provider = make_provider(text_stream())
        messages = [
            {"role": "user", "content": "read both"},
            {
                "role": "assistant",
                "content": "Reading.",
                "tool_calls": [
                    {"id": "t1", "name": "read_file", "arguments": {"file_path": "a"}},
                    {"id": "t2", "name": "read_file", "arguments": {"file_path": "b"}},
                ],
            },
            {"role": "tool", "tool_call_id": "t1", "name": "read_file", "content": "A"},
            {
                "role": "tool",
                "tool_call_id": "t2",
                "name": "read_file",
                "content": "missing",
                "is_error": True,
            },
        ]
        run(provider, messages, tools=[READ_TOOL])
        converse = provider.client.requests[0]["messages"]
        assert [m["role"] for m in converse] == ["user", "assistant", "user"]
        assert converse[1]["content"] == [
            {"text": "Reading."},
            {
                "toolUse": {
                    "toolUseId": "t1",
                    "name": "read_file",
                    "input": {"file_path": "a"},
                }
            },
            {
                "toolUse": {
                    "toolUseId": "t2",
                    "name": "read_file",
                    "input": {"file_path": "b"},
                }
            },
        ]
        results = converse[2]["content"]
        assert results[0]["toolResult"]["status"] == "success"
        assert results[1]["toolResult"] == {
            "toolUseId": "t2",
            "content": [{"text": "missing"}],
            "status": "error",
        }

    def test_merges_roles_and_wraps_late_system(self):
        provider = make_provider(text_stream())
        messages = [
            {"role": "system", "content": "base"},
            {"role": "user", "content": "one"},
            {"role": "system", "content": "plan mode"},
            {"role": "user", "content": "two"},
            {"role": "assistant", "content": ""},
            {"role": "user", "content": "three"},
        ]
        run(provider, messages)
        converse = provider.client.requests[0]["messages"]
        # Empty assistant turn dropped, everything merges into one user turn.
        assert len(converse) == 1
        texts = [b["text"] for b in converse[0]["content"]]
        assert texts[0] == "one"
        assert "<system-reminder>" in texts[1] and "plan mode" in texts[1]
        assert texts[2:] == ["two", "three"]

    def test_leading_assistant_gets_placeholder_user(self):
        provider = make_provider(text_stream())
        run(
            provider,
            [
                {"role": "assistant", "content": "earlier"},
                {"role": "user", "content": "q"},
            ],
        )
        converse = provider.client.requests[0]["messages"]
        assert converse[0]["role"] == "user"
        assert converse[1]["role"] == "assistant"

    def test_tool_history_flattened_without_tools(self):
        provider = make_provider(text_stream())
        messages = [
            {"role": "user", "content": "go"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "t1", "name": "read_file", "arguments": {}}],
            },
            {
                "role": "tool",
                "tool_call_id": "t1",
                "name": "read_file",
                "content": "data",
            },
        ]
        run(provider, messages, tools=None)
        request = provider.client.requests[0]
        assert "toolConfig" not in request
        dumped = json.dumps(request["messages"])
        assert "toolUse" not in dumped and "toolResult" not in dumped
        assert "tool_call" in dumped


class TestStreaming:
    def test_text_stream(self):
        events = run(
            make_provider(text_stream("Hi there")), [{"role": "user", "content": "x"}]
        )
        assert [e.text for e in events if isinstance(e, TextDelta)] == ["Hi there"]
        done = events[-1]
        assert isinstance(done, MessageDone)
        assert done.stop_reason == "end_turn"
        assert done.usage.input_tokens == 10 and done.usage.output_tokens == 3
        assert done.raw == {
            "provider": "bedrock",
            "model": MODEL,
            "content": [{"text": "Hi there"}],
        }
        assert sum(isinstance(e, MessageDone) for e in events) == 1

    def test_tool_call_assembly(self):
        stream = [
            {
                "contentBlockDelta": {
                    "contentBlockIndex": 0,
                    "delta": {"text": "Let me look."},
                }
            },
            {"contentBlockStop": {"contentBlockIndex": 0}},
            {
                "contentBlockStart": {
                    "contentBlockIndex": 1,
                    "start": {"toolUse": {"toolUseId": "tu1", "name": "read_file"}},
                }
            },
            {
                "contentBlockDelta": {
                    "contentBlockIndex": 1,
                    "delta": {"toolUse": {"input": '{"file_'}},
                }
            },
            {
                "contentBlockDelta": {
                    "contentBlockIndex": 1,
                    "delta": {"toolUse": {"input": 'path": "a.py"}'}},
                }
            },
            {"contentBlockStop": {"contentBlockIndex": 1}},
            {"messageStop": {"stopReason": "tool_use"}},
        ]
        events = run(
            make_provider(stream), [{"role": "user", "content": "x"}], tools=[READ_TOOL]
        )
        calls = [e.call for e in events if isinstance(e, ToolCallEvent)]
        assert len(calls) == 1
        assert calls[0].id == "tu1" and calls[0].name == "read_file"
        assert (
            calls[0].arguments == {"file_path": "a.py"} and calls[0].parse_error is None
        )
        done = events[-1]
        assert done.stop_reason == "tool_use"
        assert done.raw["content"][1] == {
            "toolUse": {
                "toolUseId": "tu1",
                "name": "read_file",
                "input": {"file_path": "a.py"},
            }
        }

    def test_bad_tool_json_sets_parse_error(self):
        stream = [
            {
                "contentBlockStart": {
                    "contentBlockIndex": 0,
                    "start": {"toolUse": {"toolUseId": "tu1", "name": "read_file"}},
                }
            },
            {
                "contentBlockDelta": {
                    "contentBlockIndex": 0,
                    "delta": {"toolUse": {"input": '{"a": '}},
                }
            },
            {"contentBlockStop": {"contentBlockIndex": 0}},
            {"messageStop": {"stopReason": "max_tokens"}},
        ]
        events = run(
            make_provider(stream), [{"role": "user", "content": "x"}], tools=[READ_TOOL]
        )
        call = next(e.call for e in events if isinstance(e, ToolCallEvent))
        assert call.parse_error and call.arguments == {}
        assert events[-1].stop_reason == "max_tokens"

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("end_turn", "end_turn"),
            ("stop_sequence", "end_turn"),
            ("tool_use", "tool_use"),
            ("max_tokens", "max_tokens"),
            ("guardrail_intervened", "refusal"),
            ("content_filtered", "refusal"),
            ("model_context_window_exceeded", "model_context_window_exceeded"),
        ],
    )
    def test_stop_reason_mapping(self, raw, expected):
        events = run(
            make_provider(text_stream(stop=raw)), [{"role": "user", "content": "x"}]
        )
        assert events[-1].stop_reason == expected
        if expected == "refusal":
            assert events[-1].detail

    def test_in_stream_exception_event(self):
        stream = [{"modelStreamErrorException": {"message": "model blew up"}}]
        with pytest.raises(ProviderError, match="model blew up"):
            run(make_provider(stream), [{"role": "user", "content": "x"}])


class TestReasoning:
    def reasoning_stream(self):
        return [
            {
                "contentBlockDelta": {
                    "contentBlockIndex": 0,
                    "delta": {"reasoningContent": {"text": "think"}},
                }
            },
            {
                "contentBlockDelta": {
                    "contentBlockIndex": 0,
                    "delta": {"reasoningContent": {"signature": "sig"}},
                }
            },
            {"contentBlockStop": {"contentBlockIndex": 0}},
            {
                "contentBlockDelta": {
                    "contentBlockIndex": 1,
                    "delta": {"reasoningContent": {"redactedContent": b"\x00secret"}},
                }
            },
            {"contentBlockStop": {"contentBlockIndex": 1}},
            {
                "contentBlockDelta": {
                    "contentBlockIndex": 2,
                    "delta": {"text": "Answer"},
                }
            },
            {"contentBlockStop": {"contentBlockIndex": 2}},
            {"messageStop": {"stopReason": "end_turn"}},
        ]

    def test_reasoning_round_trip(self):
        provider = make_provider(self.reasoning_stream(), text_stream())
        events = run(provider, [{"role": "user", "content": "q"}])
        assert [e.text for e in events if isinstance(e, ThinkingDelta)] == ["think"]
        raw = events[-1].raw
        json.dumps(raw)  # must be storable in a conversation file
        assert raw["content"][0] == {
            "reasoningContent": {"reasoningText": {"text": "think", "signature": "sig"}}
        }
        assert (
            raw["content"][1]["reasoningContent"]["redactedContentB64"]
            == base64.b64encode(b"\x00secret").decode()
        )

        history = [
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "Answer", "raw": raw},
            {"role": "user", "content": "next"},
        ]
        run(provider, history)
        replayed = provider.client.requests[1]["messages"][1]["content"]
        assert replayed[0] == raw["content"][0]
        assert replayed[1] == {"reasoningContent": {"redactedContent": b"\x00secret"}}
        assert replayed[2] == {"text": "Answer"}

    def test_raw_ignored_for_other_model(self):
        provider = make_provider(text_stream())
        raw = {
            "provider": "bedrock",
            "model": "other-model",
            "content": [{"text": "zzz"}],
        }
        run(
            provider,
            [
                {"role": "user", "content": "q"},
                {"role": "assistant", "content": "Answer", "raw": raw},
                {"role": "user", "content": "next"},
            ],
        )
        assert provider.client.requests[0]["messages"][1]["content"] == [
            {"text": "Answer"}
        ]

    def test_strip_and_retry_on_signature_error(self):
        provider = make_provider(
            FakeClientError(
                "ValidationException", "Invalid signature in thinking block"
            ),
            text_stream(),
        )
        raw = {
            "provider": "bedrock",
            "model": MODEL,
            "content": [
                {
                    "reasoningContent": {
                        "reasoningText": {"text": "t", "signature": "s"}
                    }
                },
                {"text": "Answer"},
            ],
        }
        events = run(
            provider,
            [
                {"role": "user", "content": "q"},
                {"role": "assistant", "content": "Answer", "raw": raw},
                {"role": "user", "content": "next"},
            ],
        )
        assert isinstance(events[-1], MessageDone)
        first, second = provider.client.requests
        assert "reasoningContent" in json.dumps(first["messages"], default=str)
        assert second["messages"][1]["content"] == [{"text": "Answer"}]

    def test_unrelated_validation_error_not_retried(self):
        provider = make_provider(FakeClientError("ValidationException", "bad model id"))
        with pytest.raises(ProviderError, match="ValidationException"):
            run(provider, [{"role": "user", "content": "q"}])
        assert len(provider.client.requests) == 1


class TestErrors:
    def test_throttle_retries_then_succeeds(self):
        provider = make_provider(
            FakeClientError("ThrottlingException"),
            FakeClientError("ThrottlingException"),
            text_stream(),
        )
        events = run(provider, [{"role": "user", "content": "q"}])
        assert isinstance(events[-1], MessageDone)
        assert len(provider.client.requests) == 3

    def test_throttle_gives_up(self):
        provider = make_provider(*[FakeClientError("ThrottlingException")] * 3)
        with pytest.raises(ProviderError, match="ThrottlingException"):
            run(provider, [{"role": "user", "content": "q"}])
        assert len(provider.client.requests) == 3

    def test_access_denied_hint(self):
        provider = make_provider(FakeClientError("AccessDeniedException", "no access"))
        with pytest.raises(ProviderError) as exc:
            run(provider, [{"role": "user", "content": "q"}])
        assert "model access" in str(exc.value)
        assert "InvokeModelWithResponseStream" in str(exc.value)

    def test_expired_token_hint_names_profile(self):
        provider = BedrockProvider(
            model=MODEL,
            profile="work-sso",
            client=FakeClient(FakeClientError("ExpiredTokenException", "expired")),
        )
        with pytest.raises(ProviderError, match="aws sso login --profile work-sso"):
            run(provider, [{"role": "user", "content": "q"}])

    def test_expired_credentials_are_reloaded_once(self):
        provider = make_provider(FakeClientError("ExpiredTokenException", "expired"))
        provider._can_reload = True
        fresh = FakeClient(text_stream("after refresh"))
        provider._make_client = lambda: fresh
        events = run(provider, [{"role": "user", "content": "q"}])
        assert provider.client is fresh
        assert any(getattr(e, "text", "") == "after refresh" for e in events)

    def test_still_expired_after_reload_raises(self):
        provider = make_provider(FakeClientError("ExpiredTokenException", "expired"))
        provider._can_reload = True
        provider._make_client = lambda: FakeClient(
            FakeClientError("ExpiredTokenException", "expired")
        )
        with pytest.raises(ProviderError, match="/login"):
            run(provider, [{"role": "user", "content": "q"}])

    def test_no_credentials_hint(self):
        provider = make_provider(NoCredentialsError("Unable to locate credentials"))
        with pytest.raises(ProviderError, match="No AWS credentials"):
            run(provider, [{"role": "user", "content": "q"}])

    def test_missing_model_rejected(self):
        provider = BedrockProvider(model="", client=FakeClient())
        with pytest.raises(ProviderError, match="bedrock_model"):
            run(provider, [{"role": "user", "content": "q"}])

    def test_expired_credentials_prompt_for_new_ones(self):
        provider = make_provider(
            FakeClientError("ExpiredTokenException", "expired"),
        )
        provider._can_reload = True
        clients = [
            FakeClient(FakeClientError("ExpiredTokenException", "expired")),
            FakeClient(text_stream("pasted ok")),
        ]
        provider._make_client = lambda: clients.pop(0)
        asked = []
        provider.on_credentials_expired = lambda p: asked.append(1) or True
        events = run(provider, [{"role": "user", "content": "q"}])
        assert asked == [1]
        assert any(getattr(e, "text", "") == "pasted ok" for e in events)


class TestMisc:
    def test_metadata(self):
        meta = BedrockProvider.METADATA
        assert meta.name == "bedrock"
        assert [f["key"] for f in meta.secret_fields] == ["bedrock_aws_credentials"]
        keys = {f["key"] for f in meta.config_fields}
        assert keys == {
            "bedrock_model",
            "bedrock_region",
            "bedrock_profile",
            "bedrock_credentials_file",
            "bedrock_aws_credentials",
        }

    def test_credential_sources(self, tmp_path):
        pytest.importorskip("boto3")
        env = tmp_path / ".env.work"
        env.write_text(
            "export AWS_ACCESS_KEY_ID=AKIAFILE\nexport AWS_SECRET_ACCESS_KEY=s\n"
            "AWS_REGION=us-gov-west-1\n"
        )
        from_file = BedrockProvider(
            model=MODEL, credentials_file=str(env), client=FakeClient()
        )
        assert from_file.explicit_credentials()["AWS_ACCESS_KEY_ID"] == "AKIAFILE"
        assert from_file._get_session().region_name == "us-gov-west-1"
        assert "credentials file" in from_file.credential_source()

        pasted = BedrockProvider(
            model=MODEL,
            aws_credentials='{"AWS_ACCESS_KEY_ID": "AKIAPASTE", '
            '"AWS_SECRET_ACCESS_KEY": "s"}',
            region="us-east-1",
            client=FakeClient(),
        )
        creds = pasted._get_session().get_credentials()
        assert creds.access_key == "AKIAPASTE"

        # A profile wins over everything else.
        profiled = BedrockProvider(
            model=MODEL, profile="work", credentials_file=str(env), client=FakeClient()
        )
        assert profiled.explicit_credentials() == {}

    def test_names(self):
        provider = make_provider()
        assert provider.provider_name == "bedrock"
        assert provider.model_name == MODEL
        provider.set_model("other")
        assert provider.model_name == "other"

    def test_list_models_best_effort(self):
        class Control:
            def list_inference_profiles(self):
                return {"inferenceProfileSummaries": [{"inferenceProfileId": "us.a"}]}

            def list_foundation_models(self, **kwargs):
                return {
                    "modelSummaries": [
                        {"modelId": "m.stream", "responseStreamingSupported": True},
                        {"modelId": "m.nostream", "responseStreamingSupported": False},
                    ]
                }

        class Session:
            def client(self, name):
                assert name == "bedrock"
                return Control()

            def get_credentials(self):
                return object()

        provider = make_provider()
        provider._session = Session()
        assert provider.list_models() == ["m.stream", "us.a"]
        assert provider.is_healthy() is True

    def test_list_models_error_returns_empty(self):
        class Session:
            def client(self, name):
                raise RuntimeError("nope")

            def get_credentials(self):
                return None

        provider = make_provider()
        provider._session = Session()
        assert provider.list_models() == []
        assert provider.is_healthy() is False


def test_garbled_tool_names_are_made_valid_for_replay():
    from kubrick_cli.providers.bedrock_provider import _wire_tool_name

    assert _wire_tool_name("read_file") == "read_file"
    assert _wire_tool_name("weird name!") == "weird_name_"
    assert _wire_tool_name("") == "unknown_tool"


def test_model_without_tool_support_triggers_text_fallback():
    from kubrick_cli.providers.base import ToolsNotSupportedError

    provider = make_provider(
        FakeClientError(
            "ValidationException",
            "This model doesn't support tool use in streaming mode.",
        )
    )
    with pytest.raises(ToolsNotSupportedError):
        run(provider, [{"role": "user", "content": "q"}], tools=[READ_TOOL])


def test_nova_thinking_tags_become_reasoning():
    from kubrick_cli.messages import TextDelta, ThinkingDelta

    provider = make_provider(text_stream("<thinking>check the docs</thinking>Done."))
    events = run(provider, [{"role": "user", "content": "q"}])
    assert "".join(e.text for e in events if isinstance(e, ThinkingDelta)) == (
        "check the docs"
    )
    assert "".join(e.text for e in events if isinstance(e, TextDelta)) == "Done."


def test_switches_to_inference_profile_when_required():
    provider = make_provider(
        FakeClientError(
            "ValidationException",
            "Invocation of model ID moonshotai.kimi-k3 with on-demand throughput isn't "
            "supported. Retry your request with the ID or ARN of an inference profile "
            "that contains this model.",
        ),
        text_stream("ok"),
    )
    provider._model_name = "moonshotai.kimi-k3"
    run(provider, [{"role": "user", "content": "q"}])
    assert provider.model_name == "us.moonshotai.kimi-k3"
    assert provider.client.requests[-1]["modelId"] == "us.moonshotai.kimi-k3"


def test_account_without_model_access_gets_specific_hint():
    provider = make_provider(
        FakeClientError(
            "AccessDeniedException",
            "anthropic.claude-sonnet-5-5 is not available for this account.",
        )
    )
    with pytest.raises(ProviderError, match="use-case form"):
        run(provider, [{"role": "user", "content": "q"}])
