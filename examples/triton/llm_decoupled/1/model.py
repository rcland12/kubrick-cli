"""Example Triton Python-backend model that streams chat completions for Kubrick.

Protocol (see docs/TRITON.md):
- input  ``text_input``: JSON-encoded list of {"role", "content"} messages
- request parameters: ``streaming``, ``temperature``, ``max_tokens``
- output ``text_output``: one JSON chunk per response
  {"type": "chunk", "content": "..."} ... then {"type": "complete"}
  or {"type": "error", "content": "..."}

Requires torch + transformers + accelerate in the Triton image (the stock
nvcr.io/nvidia/tritonserver:<yy.mm>-py3 image does not include them).
"""

import json
from threading import Thread

import numpy as np
import torch
import triton_python_backend_utils as pb_utils
from transformers import AutoModelForCausalLM, AutoTokenizer, TextIteratorStreamer

MODEL_ID = "Qwen/Qwen2.5-Coder-7B-Instruct"  # anything that fits your GPU in bf16


class TritonPythonModel:
    def initialize(self, args):
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
        self.model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID, torch_dtype=torch.bfloat16, device_map="cuda"
        )

    def _send(self, sender, payload):
        out = pb_utils.Tensor(
            "text_output",
            np.array([json.dumps(payload).encode("utf-8")], dtype=np.object_),
        )
        sender.send(pb_utils.InferenceResponse(output_tensors=[out]))

    def execute(self, requests):
        # Decoupled models answer through each request's response sender and
        # return None from execute().
        for request in requests:
            sender = request.get_response_sender()
            try:
                # dims [1] with max_batch_size 0 -> shape (1,), so index [0].
                raw = pb_utils.get_input_tensor_by_name(
                    request, "text_input"
                ).as_numpy()[0]
                messages = json.loads(raw.decode("utf-8"))
                params = json.loads(request.parameters() or "{}")

                inputs = self.tokenizer.apply_chat_template(
                    messages,
                    add_generation_prompt=True,
                    return_tensors="pt",
                    return_dict=True,
                ).to(self.model.device)
                streamer = TextIteratorStreamer(
                    self.tokenizer, skip_prompt=True, skip_special_tokens=True
                )
                temperature = float(params.get("temperature", 0.7))
                Thread(
                    target=self.model.generate,
                    kwargs=dict(
                        **inputs,
                        streamer=streamer,
                        max_new_tokens=int(params.get("max_tokens", 2048)),
                        do_sample=temperature > 0,
                        temperature=temperature if temperature > 0 else None,
                    ),
                ).start()

                for text in streamer:
                    if text:
                        self._send(sender, {"type": "chunk", "content": text})
                self._send(sender, {"type": "complete"})
            except Exception as e:
                self._send(sender, {"type": "error", "content": str(e)})
            finally:
                sender.send(flags=pb_utils.TRITONSERVER_RESPONSE_COMPLETE_FINAL)
        return None
