import json

from f5_ai_gateway_sdk import RequestInput
from f5_ai_gateway_sdk.parameters import Parameters
from f5_ai_gateway_sdk.processor import Processor, Request
from f5_ai_gateway_sdk.request_input import RequestInput
from f5_ai_gateway_sdk.response_output import ResponseOutput
from f5_ai_gateway_sdk.result import Result, Reject, RejectCode
from f5_ai_gateway_sdk.signature import BOTH_SIGNATURE, Signature
# from f5_ai_gateway_sdk.tags import Tags
from f5_ai_gateway_sdk.tags import Tags
from f5_ai_gateway_sdk.type_hints import Metadata

from pangea.response import PangeaResponse
from pangea.services.ai_guard import TextGuardResult
from pangea.asyncio.services.ai_guard import AIGuardAsync
from pydantic import Field

class GuardResult(TextGuardResult):
    transformed: bool

async def _guard_text(client: AIGuardAsync, body: dict) -> PangeaResponse[GuardResult]:
    return await client.request.post(
        "v1beta/guard",
        GuardResult,
        data=body
    )

def _get_tags_from_aig_result(result: GuardResult) -> Tags:
    t = Tags()

    reported: list[str] = []
    attacks: list[str] = []
    redactions: list[str] = []


    for detector_name, detector_value in dict(result.detectors).items():
        if not detector_value or not detector_value.detected:
            continue

        if hasattr(detector_value.data, "entities"):
            for entity in detector_value.data.entities:
                if entity.action == "reported":
                    reported.append(detector_name)
                if entity.action == "blocked":
                    attacks.append(detector_name)
                if "redacted" in entity.action:
                    redactions.append(detector_name)

        elif hasattr(detector_value, "action"):
            action = detector_value.action
            if action == "reported":
                reported.append(detector_name)
            if action == "blocked":
                attacks.append(detector_name)
            if "redacted" in action:
                redactions.append(detector_name)


    if reported:
        t.add_tag("pangea-ai-guard-reports", *reported)

    if redactions:
        t.add_tag("pangea-ai-guard-redactions", *redactions)
        t.add_tag("pangea-ai-guard-modified", "true")
    else:
        t.add_tag("pangea-ai-guard-modified", "false")

    if attacks:
        t.add_tag("pangea-ai-guard-attacks", *attacks)
        t.add_tag("pangea-ai-guard-blocked", "true")
        t.add_tag("attacks-detected", *attacks)
    else:
        t.add_tag("pangea-ai-guard-blocked", "false")

    return t

class AIGuardProcessorParameters(Parameters):
    request_recipe: str | None = Field(default=None, description="AI Guard Request Recipe")
    response_recipe: str | None = Field(default=None, description="AI Guard Response Recipe")

class AIGuardProcessor(Processor):
    def __init__(self, ai_guard: AIGuardAsync, signature: Signature = BOTH_SIGNATURE):
        self.ai_guard = ai_guard

        super().__init__(
            name="pangea-ai-guard",
            version="0.1.0",
            namespace="guardrails",
            signature=signature,
            parameters_class=AIGuardProcessorParameters,
        )

    async def process_input(
        self, 
        prompt: RequestInput, 
        metadata: Metadata, 
        parameters: AIGuardProcessorParameters, 
        request: Request
    ) -> Result | Reject:
        if not any((parameters.annotate, parameters.modify, parameters.reject)):
            # We literally can't take any actions, so let's just skip here
            return Result()

        print(metadata)
        print(request.client)
        print(request.headers)

        # tags = Tags()

        # No reason to bother with pydantic serializer
        messages = []
        for m in prompt.messages:
            messages.append({
                "content": m.content,
                "role": m.role,
            })

        if len(messages) == 0:
            return Result()

        aig_resp = await _guard_text(self.ai_guard, {
            "input": {
                "messages": messages
            },
            "recipe": parameters.request_recipe,
            "event_type": "input",
            "extra_info": {
                "app_name": "f5-ai-gateway",
            },
        })
        # aig_resp = self.ai_guard.guard_text(messages=messages, recipe=parameters.request_recipe)
        if not aig_resp.success or aig_resp.result is None:
            # TODO: Should this be a `Reject` or a `Result` with a tag?
            if aig_resp.pangea_error:
                detail = ", ".join([err.detail for err in aig_resp.pangea_error.errors])
            else:
                detail = "Unknown"
                return Reject(code=RejectCode.RESOURCE_AVAILABILITY, detail=f"AI Guard Failure: {detail}")

        result = aig_resp.result
        assert(result)

        tags = Tags()
        tags.add_tag("pangea-ai-guard-blocked", json.dumps(result.blocked))
        tags.add_tag("pangea-ai-guard-modified", json.dumps(result.transformed))

        if (parameters.reject or parameters.modify) and result.blocked:
            return Reject(code=RejectCode.POLICY_VIOLATION, detail="Blocked by AI Guard", tags=tags)

        modified = False
        if parameters.modify and result.transformed:
            modified = True
            messages = result.output["messages"]  # type: ignore
            # Lets see if there is any difference
            for old, new in zip(prompt.messages, messages):
                if old.content != new["content"]:
                    old.content = new["content"]

        return Result(
            modified_prompt=prompt if modified else None,
            tags=tags,
        )

    async def process_response(
        self, 
        prompt: RequestInput | None,
        response: ResponseOutput, 
        metadata: Metadata, 
        parameters: AIGuardProcessorParameters, 
        request: Request
    ) -> Result | Reject:
        if not any((parameters.annotate, parameters.modify, parameters.reject)):
            # We literally can't take any actions, so let's just skip here
            return Result()

        messages = []
        for choice in response.choices:
            m = choice.message
            messages.append({
                "content": m.content,
                "role": m.role,
            })

        if len(messages) == 0:
            return Result()

        aig_resp = await _guard_text(self.ai_guard, {
            "input": {
                "messages": messages
            },
            "recipe": parameters.response_recipe,
            "event_type": "input",
            "extra_info": {
                "app_name": "f5-ai-gateway",
            },
        })
        # aig_resp = self.ai_guard.guard_text(messages=messages, recipe=parameters.response_recipe)
        if not aig_resp.success or aig_resp.result is None:
            if aig_resp.pangea_error:
                detail = ", ".join([err.detail for err in aig_resp.pangea_error.errors])
            else:
                detail = "Unknown"
                return Reject(code=RejectCode.RESOURCE_AVAILABILITY, detail=f"AI Guard Failure: {detail}")

        result = aig_resp.result
        assert(result)

        tags = Tags()
        tags.add_tag("pangea-ai-guard-blocked", json.dumps(result.blocked))
        tags.add_tag("pangea-ai-guard-modified", json.dumps(result.transformed))

        if parameters.reject and result.blocked:
            return Reject(code=RejectCode.POLICY_VIOLATION, detail="Blocked by AI Guard", tags=tags)

        modified = False
        if parameters.modify and result.transformed:
            modified = True
            messages = result.output["messages"]  # type: ignore
            for old, new in zip(response.choices, messages):
                if old.message.content != new["content"]:
                    old.message.content = new["content"]

        return Result(
            modified_response=response if modified else None,
            tags=tags,
        )

