"""Amazon Bedrock provider adapter (Converse API).

Works with any Bedrock model that supports the Converse API with tool use
(Claude, Llama, Mistral, Nova, ...). Credentials come, in order, from a named
AWS profile, a ``.env``-style credentials file, credentials pasted into Kubrick
(kept in its encrypted store), or the standard AWS chain (environment, ``~/.aws``,
SSO, instance roles, ``AWS_BEARER_TOKEN_BEDROCK``). Requires the optional extra:
``pip install 'kubrick-cli[bedrock]'``.
"""

import base64
import copy
import os
import re
import time
from typing import Any, Callable, Dict, Iterator, List, Optional

from ..messages import (
    MessageDone,
    ThinkTagSplitter,
    ThinkingDelta,
    ToolCall,
    ToolCallEvent,
    ToolSpec,
    Usage,
    group_tool_results,
    parse_arguments,
)
from .. import aws_credentials as awscreds
from ..tool_protocol import to_plain_messages
from .base import (
    ProviderAdapter,
    ProviderError,
    ProviderMetadata,
    ToolsNotSupportedError,
)

_STOP_REASONS = {
    "end_turn": "end_turn",
    "stop_sequence": "end_turn",
    "tool_use": "tool_use",
    "max_tokens": "max_tokens",
    "guardrail_intervened": "refusal",
    "content_filtered": "refusal",
}

_THROTTLE_RETRIES = 2
# Region prefix -> cross-region inference profile prefix (checked in order).
_PROFILE_PREFIXES = {
    "us-gov-": "us-gov",
    "us-": "us",
    "ca-": "us",
    "eu-": "eu",
    "ap-": "apac",
}
_CREDENTIAL_CODES = (
    "ExpiredToken",
    "ExpiredTokenException",
    "UnrecognizedClientException",
    "InvalidSignatureException",
    "UnauthorizedSSOTokenError",
    "SSOTokenLoadError",
    "TokenRetrievalError",
)
_REDACTED_KEY = "redactedContentB64"


def _rejects_tools(message: str) -> bool:
    text = message.lower()
    return "tool" in text and any(
        phrase in text
        for phrase in ("doesn't support", "does not support", "not supported")
    )


def _wire_tool_name(name: str) -> str:
    """A tool name Converse accepts ([a-zA-Z0-9_-]+, max 64), even for garbled ones."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name or "")[:64] or "unknown_tool"


def _is_credential_error(code: str) -> bool:
    return code in _CREDENTIAL_CODES or code.startswith("ExpiredToken")


def _error_code(error: Exception) -> str:
    """Best-effort AWS error code from a botocore exception (or its class name)."""
    response = getattr(error, "response", None)
    if isinstance(response, dict):
        code = response.get("Error", {}).get("Code")
        if code:
            return code
    return type(error).__name__


def _error_message(error: Exception) -> str:
    response = getattr(error, "response", None)
    if isinstance(response, dict):
        message = response.get("Error", {}).get("Message")
        if message:
            return message
    return str(error)


class BedrockProvider(ProviderAdapter):
    """Provider adapter for Amazon Bedrock's Converse streaming API."""

    METADATA = ProviderMetadata(
        name="bedrock",
        display_name="Amazon Bedrock",
        description="AWS Bedrock Converse API (Claude, Llama, Nova, ...) via your AWS credentials",
        config_fields=[
            {
                "key": "bedrock_model",
                "label": "Model or inference profile ID",
                "type": "model",
                "help_text": (
                    "A Converse-capable model ID or inference profile ID. List them with:\n"
                    "  aws bedrock list-inference-profiles\n"
                    "  aws bedrock list-foundation-models --by-inference-type ON_DEMAND"
                ),
            },
            {
                "key": "bedrock_region",
                "label": "AWS region (blank = AWS_REGION / profile default)",
                "type": "text",
                "required": False,
                "default": "",
            },
            {
                "key": "bedrock_profile",
                "label": "AWS profile (blank = default credential chain)",
                "type": "text",
                "required": False,
                "default": "",
                "advanced": True,
            },
            {
                "key": "bedrock_credentials_file",
                "label": "Credentials file (.env with AWS_ACCESS_KEY_ID=...)",
                "type": "text",
                "required": False,
                "default": "",
                "advanced": True,
            },
            {
                "key": "bedrock_aws_credentials",
                "label": "AWS credentials",
                "type": "secret",
                "required": False,
                "advanced": True,
            },
        ],
    )

    def __init__(
        self,
        model: str = "",
        region: str = "",
        profile: str = "",
        credentials_file: str = "",
        aws_credentials: Optional[str] = None,
        client=None,
    ):
        """
        Initialize Bedrock provider.

        Args:
            model: Bedrock model ID or inference profile ID
            region: AWS region (falls back to the credentials, AWS_REGION, or profile)
            profile: AWS named profile (wins over the other credential sources)
            credentials_file: ``.env``-style file with AWS_ACCESS_KEY_ID etc.,
                re-read whenever credentials need reloading
            aws_credentials: Pasted credentials (JSON or ``KEY=VALUE`` text) from
                Kubrick's credential store
            client: Pre-built ``bedrock-runtime`` client (for tests)
        """
        self._model_name = model or ""
        self.region = region or None
        self.profile = profile or None
        self.credentials_file = credentials_file or None
        self.pasted_credentials = awscreds.from_json(aws_credentials)
        # Called (interactive sessions only) when credentials have expired; returns
        # True after the user supplied new ones (see main.KubrickCLI).
        self.on_credentials_expired: Optional[Callable[["BedrockProvider"], bool]] = (
            None
        )
        self._session = None
        self._sleep = time.sleep
        # Rebuild the client when credentials expire, so refreshed keys in
        # ~/.aws/credentials are picked up without restarting (not for test clients).
        self._can_reload = client is None
        self.client = client if client is not None else self._make_client()

    # --- Client setup ----------------------------------------------------------

    def _get_session(self):
        if self._session is None:
            try:
                import boto3
            except ImportError as e:
                raise ProviderError(
                    "The Bedrock provider needs boto3. Install it with:\n"
                    "  pip install 'kubrick-cli[bedrock]'"
                ) from e
            values = self.explicit_credentials()
            region = self.region or awscreds.region_of(values)
            try:
                if values.get("AWS_ACCESS_KEY_ID"):
                    self._session = boto3.Session(
                        aws_access_key_id=values["AWS_ACCESS_KEY_ID"],
                        aws_secret_access_key=values.get("AWS_SECRET_ACCESS_KEY"),
                        aws_session_token=values.get("AWS_SESSION_TOKEN") or None,
                        region_name=region,
                    )
                else:
                    self._session = boto3.Session(
                        profile_name=self.profile, region_name=region
                    )
            except Exception as e:
                raise ProviderError(f"Bedrock: cannot load AWS profile: {e}") from e
            if values.get("AWS_BEARER_TOKEN_BEDROCK"):
                # botocore reads Bedrock API keys from this variable.
                os.environ["AWS_BEARER_TOKEN_BEDROCK"] = values[
                    "AWS_BEARER_TOKEN_BEDROCK"
                ]
        return self._session

    def explicit_credentials(self) -> Dict[str, str]:
        """Credentials from the file or a paste (empty when using a profile/the chain)."""
        if self.profile:
            return {}
        if self.credentials_file:
            return awscreds.load_env_file(self.credentials_file)
        return dict(self.pasted_credentials)

    def credential_source(self) -> str:
        """Human description of where credentials come from."""
        if self.profile:
            return f"AWS profile {self.profile}"
        if self.credentials_file:
            return f"credentials file {self.credentials_file}"
        if self.pasted_credentials:
            return "pasted credentials (encrypted store)"
        return "default AWS chain (environment, ~/.aws, SSO)"

    def reload_credentials(self):
        """Drop the cached session and client so the next request re-reads credentials."""
        self._session = None
        self.client = self._make_client()

    def _make_client(self):
        session = self._get_session()
        try:
            from botocore.config import Config

            config = Config(
                read_timeout=900, connect_timeout=10, retries={"mode": "standard"}
            )
            return session.client("bedrock-runtime", config=config)
        except Exception as e:
            if _error_code(e) == "NoRegionError":
                raise ProviderError(
                    "Bedrock: no AWS region configured. Set bedrock_region, "
                    "AWS_REGION, or a region in your AWS profile."
                ) from e
            raise ProviderError(f"Bedrock: cannot create client: {e}") from e

    # --- Request building ------------------------------------------------------

    def _build_request(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[ToolSpec]],
        options: Optional[Dict[str, Any]],
        strip_reasoning: bool = False,
    ) -> Dict[str, Any]:
        has_tool_structure = any(
            m["role"] == "tool" or m.get("tool_calls") for m in messages
        )
        if not tools and has_tool_structure:
            # Converse rejects toolUse/toolResult history without a toolConfig.
            messages = to_plain_messages(messages)

        system: List[Dict[str, Any]] = []
        converse: List[Dict[str, Any]] = []
        leading = True
        for run in group_tool_results(messages):
            first = run[0]
            role = first["role"]
            if role == "system":
                if leading:
                    if first.get("content"):
                        system.append({"text": first["content"]})
                    continue
                blocks = [
                    {
                        "text": f"<system-reminder>\n{first['content']}\n</system-reminder>"
                    }
                ]
                self._append(converse, "user", blocks)
                continue
            leading = False
            if role == "tool":
                blocks = [self._tool_result_block(m) for m in run]
                self._append(converse, "user", blocks)
            elif role == "assistant":
                self._append(
                    converse,
                    "assistant",
                    self._assistant_blocks(first, strip_reasoning),
                )
            else:
                self._append(converse, "user", self._text_blocks(first.get("content")))

        if converse and converse[0]["role"] != "user":
            converse.insert(
                0,
                {
                    "role": "user",
                    "content": [{"text": "(earlier conversation omitted)"}],
                },
            )

        request: Dict[str, Any] = {"modelId": self._model_name, "messages": converse}
        if system:
            request["system"] = system
        if tools:
            request["toolConfig"] = {
                "tools": [
                    {
                        "toolSpec": {
                            "name": t.name,
                            "description": t.description,
                            "inputSchema": {"json": t.parameters},
                        }
                    }
                    for t in tools
                ]
            }
        inference: Dict[str, Any] = {}
        options = options or {}
        if options.get("max_tokens"):
            inference["maxTokens"] = int(options["max_tokens"])
        if options.get("temperature") is not None:
            inference["temperature"] = float(options["temperature"])
        if inference:
            request["inferenceConfig"] = inference
        return request

    @staticmethod
    def _append(
        converse: List[Dict[str, Any]], role: str, blocks: List[Dict[str, Any]]
    ):
        """Append blocks, merging into the previous message when roles repeat."""
        if not blocks:
            return
        if converse and converse[-1]["role"] == role:
            converse[-1]["content"].extend(blocks)
        else:
            converse.append({"role": role, "content": list(blocks)})

    @staticmethod
    def _text_blocks(text: Optional[str]) -> List[Dict[str, Any]]:
        return [{"text": text}] if text and text.strip() else []

    @staticmethod
    def _tool_result_block(msg: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "toolResult": {
                "toolUseId": msg["tool_call_id"],
                "content": [{"text": msg.get("content") or "(no output)"}],
                "status": "error" if msg.get("is_error") else "success",
            }
        }

    def _assistant_blocks(
        self, msg: Dict[str, Any], strip_reasoning: bool
    ) -> List[Dict[str, Any]]:
        raw = msg.get("raw")
        if (
            isinstance(raw, dict)
            and raw.get("provider") == "bedrock"
            and raw.get("model") == self._model_name
            and raw.get("content")
        ):
            blocks = []
            for block in raw["content"]:
                if "reasoningContent" in block:
                    if strip_reasoning:
                        continue
                    blocks.append(self._decode_reasoning(block))
                elif "text" in block:
                    if block["text"].strip():
                        blocks.append({"text": block["text"]})
                else:
                    block = copy.deepcopy(block)
                    if "toolUse" in block:
                        block["toolUse"]["name"] = _wire_tool_name(
                            block["toolUse"].get("name", "")
                        )
                    blocks.append(block)
            if blocks:
                return blocks

        blocks = self._text_blocks(msg.get("content"))
        for call in msg.get("tool_calls") or []:
            blocks.append(
                {
                    "toolUse": {
                        "toolUseId": call["id"],
                        "name": _wire_tool_name(call["name"]),
                        "input": call.get("arguments") or {},
                    }
                }
            )
        return blocks

    @staticmethod
    def _decode_reasoning(block: Dict[str, Any]) -> Dict[str, Any]:
        reasoning = block["reasoningContent"]
        if _REDACTED_KEY in reasoning:
            return {
                "reasoningContent": {
                    "redactedContent": base64.b64decode(reasoning[_REDACTED_KEY])
                }
            }
        return copy.deepcopy(block)

    # --- Streaming -------------------------------------------------------------

    def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[ToolSpec]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Iterator[Any]:
        """Stream one response from the Converse API."""
        response = self._start_stream(messages, tools, options)
        yield from self._consume(response.get("stream") or [])

    def _start_stream(self, messages, tools, options) -> Dict[str, Any]:
        """Call converse_stream with throttle retries and one strip-and-retry."""
        if not self._model_name:
            raise ProviderError(
                "Bedrock needs a model or inference profile ID (bedrock_model)."
            )
        strip = False
        throttle_attempts = 0
        reloaded = False
        prompts = 0
        left = awscreds.seconds_left(self.explicit_credentials())
        if left is not None and left < 30 and self._ask_for_new_credentials():
            prompts += 1
        while True:
            request = self._build_request(
                messages, tools, options, strip_reasoning=strip
            )
            try:
                return self.client.converse_stream(**request)
            except Exception as e:
                code = _error_code(e)
                message = _error_message(e)
                if (
                    code == "ThrottlingException"
                    and throttle_attempts < _THROTTLE_RETRIES
                ):
                    throttle_attempts += 1
                    self._sleep(2**throttle_attempts)
                    continue
                if (
                    code == "ValidationException"
                    and not strip
                    and any(
                        w in message.lower()
                        for w in ("thinking", "signature", "reasoning")
                    )
                ):
                    # Replayed reasoning blocks were rejected (e.g. the history
                    # was trimmed); drop them once and retry.
                    strip = True
                    continue
                profile_id = self._inference_profile_for(message)
                if code == "ValidationException" and profile_id:
                    # Some models can only be called through a cross-region
                    # inference profile ("us.<model>"); switch once and retry.
                    self._model_name = profile_id
                    continue
                if code == "ValidationException" and tools and _rejects_tools(message):
                    raise ToolsNotSupportedError(
                        f"{self._model_name} doesn't support tool use on Bedrock: {message}"
                    ) from e
                if _is_credential_error(code) and self._can_reload:
                    # Short-lived keys (STS, 8-hour work credentials) may have been
                    # refreshed on disk since the client was created; reload once,
                    # then ask the user (interactive sessions) for new ones.
                    if not reloaded:
                        reloaded = True
                        self.reload_credentials()
                        continue
                    if prompts < 2 and self._ask_for_new_credentials():
                        prompts += 1
                        continue
                raise self._translate_error(e) from e

    def _inference_profile_for(self, message: str) -> Optional[str]:
        """``us.<model>`` when Bedrock says the bare model needs an inference profile."""
        text = message.lower()
        if "inference profile" not in text or "on-demand" not in text:
            return None
        if self._model_name.split(".", 1)[0] in _PROFILE_PREFIXES.values():
            return None  # already a profile ID
        region = self.region or self._get_session().region_name or ""
        prefix = next(
            (p for r, p in _PROFILE_PREFIXES.items() if region.startswith(r)), None
        )
        return f"{prefix}.{self._model_name}" if prefix else None

    def _ask_for_new_credentials(self) -> bool:
        if self.on_credentials_expired is None or not self._can_reload:
            return False
        if not self.on_credentials_expired(self):
            return False
        self.reload_credentials()
        return True

    def _consume(self, stream) -> Iterator[Any]:
        blocks: Dict[int, Dict[str, Any]] = {}
        stop_reason = "end_turn"
        detail = None
        usage = None
        splitter = ThinkTagSplitter()
        try:
            for event in stream:
                if "contentBlockStart" in event:
                    start = event["contentBlockStart"]
                    tool = start.get("start", {}).get("toolUse")
                    if tool:
                        blocks[start.get("contentBlockIndex", len(blocks))] = {
                            "kind": "tool",
                            "id": tool.get("toolUseId", ""),
                            "name": tool.get("name", ""),
                            "input": "",
                        }
                elif "contentBlockDelta" in event:
                    payload = event["contentBlockDelta"]
                    index = payload.get("contentBlockIndex", 0)
                    delta = payload.get("delta", {})
                    if "text" in delta:
                        block = blocks.setdefault(index, {"kind": "text", "text": ""})
                        block["text"] += delta["text"]
                        if delta["text"]:
                            yield from splitter.feed(delta["text"])
                    elif "toolUse" in delta:
                        block = blocks.setdefault(
                            index, {"kind": "tool", "id": "", "name": "", "input": ""}
                        )
                        block["input"] += delta["toolUse"].get("input", "")
                    elif "reasoningContent" in delta:
                        block = blocks.setdefault(
                            index,
                            {
                                "kind": "reasoning",
                                "text": "",
                                "signature": "",
                                "redacted": b"",
                            },
                        )
                        reasoning = delta["reasoningContent"]
                        if reasoning.get("text"):
                            block["text"] += reasoning["text"]
                            yield ThinkingDelta(reasoning["text"])
                        if reasoning.get("signature"):
                            block["signature"] += reasoning["signature"]
                        if reasoning.get("redactedContent"):
                            block["redacted"] += reasoning["redactedContent"]
                elif "contentBlockStop" in event:
                    index = event["contentBlockStop"].get("contentBlockIndex", 0)
                    block = blocks.get(index)
                    if block and block["kind"] == "tool" and not block.get("emitted"):
                        block["emitted"] = True
                        yield ToolCallEvent(self._finish_tool(block))
                elif "messageStop" in event:
                    raw_reason = event["messageStop"].get("stopReason", "end_turn")
                    stop_reason = _STOP_REASONS.get(raw_reason, raw_reason)
                    if stop_reason == "refusal":
                        detail = f"Bedrock stopped the response ({raw_reason})."
                elif "metadata" in event:
                    u = event["metadata"].get("usage", {})
                    usage = Usage(
                        input_tokens=u.get("inputTokens", 0),
                        output_tokens=u.get("outputTokens", 0),
                        cache_read_tokens=u.get("cacheReadInputTokens", 0),
                        cache_write_tokens=u.get("cacheWriteInputTokens", 0),
                    )
                else:
                    # In-stream exception events, e.g. {"throttlingException": {...}}
                    for key, value in event.items():
                        if key.endswith("Exception"):
                            message = (
                                value.get("message", "")
                                if isinstance(value, dict)
                                else ""
                            )
                            code = key[0].upper() + key[1:]
                            raise ProviderError(f"Bedrock {code}: {message}")
        except ProviderError:
            raise
        except Exception as e:
            raise self._translate_error(e) from e

        yield from splitter.flush()

        # Tool blocks whose stop event never arrived still need answering.
        for index in sorted(blocks):
            block = blocks[index]
            if block["kind"] == "tool" and not block.get("emitted"):
                block["emitted"] = True
                yield ToolCallEvent(self._finish_tool(block))

        raw_content = [self._raw_block(blocks[i]) for i in sorted(blocks)]
        raw_content = [b for b in raw_content if b is not None]
        yield MessageDone(
            stop_reason=stop_reason,
            usage=usage,
            raw={
                "provider": "bedrock",
                "model": self._model_name,
                "content": raw_content,
            },
            detail=detail,
        )

    @staticmethod
    def _finish_tool(block: Dict[str, Any]) -> ToolCall:
        try:
            arguments = parse_arguments(block["input"])
            error = None
        except (ValueError, TypeError) as e:
            arguments, error = {}, f"invalid tool arguments: {e}"
        block["arguments"] = arguments
        return ToolCall(block["id"], block["name"], arguments, parse_error=error)

    @staticmethod
    def _raw_block(block: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        kind = block["kind"]
        if kind == "text":
            return {"text": block["text"]} if block["text"] else None
        if kind == "tool":
            return {
                "toolUse": {
                    "toolUseId": block["id"],
                    "name": block["name"],
                    "input": block.get("arguments", {}),
                }
            }
        if block["redacted"]:
            return {
                "reasoningContent": {
                    _REDACTED_KEY: base64.b64encode(block["redacted"]).decode("ascii")
                }
            }
        text = {"text": block["text"]}
        if block["signature"]:
            text["signature"] = block["signature"]
        return {"reasoningContent": {"reasoningText": text}}

    # --- Errors ----------------------------------------------------------------

    def _translate_error(self, error: Exception) -> ProviderError:
        code = _error_code(error)
        message = _error_message(error)
        profile_flag = f" --profile {self.profile}" if self.profile else ""
        if (
            code == "AccessDeniedException"
            and "not available for this account" in message
        ):
            hint = (
                "This AWS account isn't enabled for that model. Request access in the "
                "Bedrock console's model catalog (Anthropic models need a one-time "
                "use-case form; some need an AWS Marketplace subscription), or pick "
                "another model with /model."
            )
        elif code == "AccessDeniedException":
            hint = (
                "Check that model access is enabled for this model in the Bedrock console "
                "and that your IAM identity allows bedrock:InvokeModelWithResponseStream."
            )
        elif _is_credential_error(code):
            if self.profile:
                hint = (
                    "Your AWS credentials are invalid or expired. Refresh the profile "
                    f"(~/.aws/credentials, or aws sso login{profile_flag})."
                )
            elif self.credentials_file:
                hint = (
                    f"Your AWS credentials are invalid or expired. Put new ones in "
                    f"{self.credentials_file} (Kubrick re-reads it) or run /login."
                )
            else:
                hint = (
                    "Your AWS credentials are invalid or expired. Paste new ones with "
                    "/login (or `kubrick auth login bedrock`); environment variables "
                    "need a restart."
                )
        elif code in ("NoCredentialsError", "PartialCredentialsError"):
            hint = (
                "No AWS credentials found. Configure a profile (aws configure / "
                f"aws sso login{profile_flag}) or set AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY."
            )
        elif code == "ResourceNotFoundException":
            hint = "Check bedrock_model and bedrock_region; the model may not exist in this region."
        else:
            hint = ""
        text = f"Bedrock {code}: {message}"
        return ProviderError(f"{text}\n{hint}" if hint else text)

    # --- Misc ------------------------------------------------------------------

    def is_healthy(self) -> bool:
        """True if AWS credentials can be resolved."""
        try:
            return self._get_session().get_credentials() is not None
        except Exception:
            return False

    def list_models(self) -> List[str]:
        """Inference profiles plus on-demand streaming text models (best effort)."""
        try:
            control = self._get_session().client("bedrock")
        except Exception:
            return []
        models = set()
        try:
            for profile in control.list_inference_profiles().get(
                "inferenceProfileSummaries", []
            ):
                if profile.get("inferenceProfileId"):
                    models.add(profile["inferenceProfileId"])
        except Exception:
            pass
        try:
            summaries = control.list_foundation_models(
                byOutputModality="TEXT", byInferenceType="ON_DEMAND"
            ).get("modelSummaries", [])
            for summary in summaries:
                if summary.get("responseStreamingSupported") and summary.get("modelId"):
                    models.add(summary["modelId"])
        except Exception:
            pass
        return sorted(models)

    @property
    def provider_name(self) -> str:
        """Get provider name."""
        return "bedrock"

    @property
    def model_name(self) -> str:
        """Get model name."""
        return self._model_name
