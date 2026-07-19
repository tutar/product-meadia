from collections.abc import Awaitable, Callable
from contextvars import ContextVar, Token
from typing import Any

GenerationRecorder = Callable[[str, str, dict, dict, dict], Awaitable[None]]
_recorder: ContextVar[GenerationRecorder | None] = ContextVar("generation_recorder", default=None)
_substep: ContextVar[str | None] = ContextVar("generation_substep", default=None)


def set_generation_recorder(recorder: GenerationRecorder) -> Token:
    return _recorder.set(recorder)


def reset_generation_recorder(token: Token) -> None:
    _recorder.reset(token)


def set_generation_substep(substep: str) -> Token:
    return _substep.set(substep)


def reset_generation_substep(token: Token) -> None:
    _substep.reset(token)


def generation_substep() -> str | None:
    return _substep.get()


async def record_generation(provider: str, model: str, parameters: dict, normalized_input: dict, normalized_output: dict, provider_payload: dict) -> None:
    recorder = _recorder.get()
    if recorder:
        await recorder(provider, model, parameters, normalized_input, normalized_output, provider_payload)
