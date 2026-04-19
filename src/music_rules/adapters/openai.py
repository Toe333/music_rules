"""OpenAI-compatible function-calling adapter.

Re-uses :mod:`music_rules.adapters.mcp`'s tool registry so MCP and
OpenAI clients always share the exact same surface — there's no
"OpenAI-only tool that drifted from MCP" failure mode.

Public API
==========

* :func:`get_tools_schema` — return the full tool catalogue in OpenAI's
  ``[{"type": "function", "function": {...}}]`` schema, ready to pass
  as ``tools=`` in ``openai.ChatCompletion.create(...)`` or any
  drop-in replacement (Groq, Together, Ollama, vLLM, LiteLLM, …).

* :func:`get_tool_schema(name)` — single-tool variant (handy for tests
  and for clients that hand-pick which tools to expose).

* :func:`dispatch(name, arguments)` — invoke a tool by name with a
  validated argument dict and return its JSON-serializable result.
  This is the *only* function model code should call to actually run
  a tool — it normalizes every tool's failure mode (missing args,
  unknown tool, validation error) into an exception with a clear
  message.

Two-line example
----------------

::

    from music_rules.adapters import openai as mr_openai

    tools  = mr_openai.get_tools_schema()
    result = mr_openai.dispatch("evaluate_passage", {"piece": piece})

To wire into LiteLLM::

    import litellm
    response = litellm.completion(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Grade this counterpoint"}],
        tools=mr_openai.get_tools_schema(),
    )
    for call in response.choices[0].message.tool_calls or []:
        out = mr_openai.dispatch(call.function.name, json.loads(call.function.arguments))

Schema generation
-----------------

We don't pull in extra dependencies (no Pydantic models per tool, no
``griffe``) — instead we read each tool function's signature with
:mod:`inspect` and convert its type hints into JSON Schema using a
small, well-tested mapper at the bottom of this module. That keeps
the schema in lock-step with the actual Python signatures: change a
parameter and the schema updates automatically on next call.
"""

from __future__ import annotations

import inspect
import types
import typing
from typing import Any, Literal, Union, get_args, get_origin

from music_rules.adapters import mcp as _mcp_adapter

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_tools_schema() -> list[dict[str, Any]]:
    """Return the full OpenAI function-calling schema for every tool.

    Each entry is a dict with the structure OpenAI expects::

        {
          "type": "function",
          "function": {
            "name":        "<tool name>",
            "description": "<tool docstring>",
            "parameters":  { "type": "object", "properties": {...}, "required": [...] }
          }
        }

    The list mirrors :func:`music_rules.adapters.mcp.list_tool_names`
    one-to-one and in the same order.
    """
    return [
        _function_schema(name, fn) for name, fn in _mcp_adapter._TOOLS.items()
    ]


def get_tool_schema(name: str) -> dict[str, Any]:
    """Return the OpenAI schema for a single tool by name.

    Raises:
        KeyError: if ``name`` isn't a registered tool.
    """
    try:
        fn = _mcp_adapter._TOOLS[name]
    except KeyError as exc:
        raise KeyError(
            f"Unknown tool: {name!r}. "
            f"Available: {', '.join(sorted(_mcp_adapter._TOOLS))}"
        ) from exc
    return _function_schema(name, fn)


def list_tool_names() -> list[str]:
    """Return every tool name this adapter exposes (mirrors the MCP adapter)."""
    return _mcp_adapter.list_tool_names()


def dispatch(name: str, arguments: dict[str, Any] | None = None) -> Any:
    """Execute a tool by name with a dict of arguments.

    Args:
        name:      the OpenAI ``function.name`` from the model's tool call.
        arguments: the JSON-decoded ``function.arguments`` (or ``None``
                   for zero-arg tools).

    Returns:
        The tool's return value (JSON-serializable).

    Raises:
        KeyError:   unknown tool name.
        TypeError:  arguments don't match the tool's signature.
    """
    return _mcp_adapter.call_tool(name, arguments)


# ---------------------------------------------------------------------------
# Schema generation
# ---------------------------------------------------------------------------


def _function_schema(name: str, fn: Any) -> dict[str, Any]:
    """Build a single-tool OpenAI schema from a Python function."""
    sig = inspect.signature(fn)
    # Resolve string-form annotations (PEP 563 / 649) to actual types.
    # Using include_extras=True keeps Annotated[...] metadata if a tool
    # ever wants to attach validation hints to a parameter later.
    try:
        hints = typing.get_type_hints(fn, include_extras=True)
    except Exception:
        hints = {}

    properties: dict[str, dict[str, Any]] = {}
    required: list[str] = []

    for pname, param in sig.parameters.items():
        if pname == "self":
            continue
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue  # *args / **kwargs aren't expressible in JSON Schema

        annotation = hints.get(pname, param.annotation)
        if annotation is inspect.Parameter.empty:
            annotation = Any  # be permissive rather than refuse to schema-ify

        prop = _annotation_to_jsonschema(annotation)
        if param.default is not inspect.Parameter.empty:
            prop = {**prop, "default": _jsonable_default(param.default)}
        else:
            required.append(pname)

        properties[pname] = prop

    description = _first_doc_paragraph(fn)
    schema: dict[str, Any] = {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
            },
        },
    }
    if required:
        schema["function"]["parameters"]["required"] = required
    return schema


def _first_doc_paragraph(fn: Any) -> str:
    """Return the first paragraph of ``fn.__doc__`` (or an empty string)."""
    doc = inspect.getdoc(fn) or ""
    return doc.split("\n\n", 1)[0].strip()


def _jsonable_default(value: Any) -> Any:
    """Coerce a Python default into a JSON-Schema-friendly value."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable_default(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable_default(v) for k, v in value.items()}
    return str(value)


# Map of leaf Python types → JSON Schema fragments.
_PRIMITIVE_TYPES: dict[type, dict[str, Any]] = {
    int: {"type": "integer"},
    float: {"type": "number"},
    str: {"type": "string"},
    bool: {"type": "boolean"},
    type(None): {"type": "null"},
}


def _annotation_to_jsonschema(annotation: Any) -> dict[str, Any]:
    """Convert a Python typing annotation to a JSON Schema fragment.

    Supports:
        * primitives: ``int``, ``float``, ``str``, ``bool``, ``None``
        * containers: ``list[X]``, ``dict[str, X]``, ``tuple[X, ...]``
        * unions:     ``X | Y``, ``Optional[X]``, ``Union[X, Y]``
        * literals:   ``Literal["a", "b", 1]``
        * fallback:   anything unknown becomes ``{}`` (no constraint).
    """
    if annotation is Any:
        return {}

    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin is Literal:
        return _literal_schema(args)

    if origin in (Union, types.UnionType):
        return _union_schema(args)

    if origin in (list, list):
        item_schema = _annotation_to_jsonschema(args[0]) if args else {}
        return {"type": "array", "items": item_schema}

    if origin in (tuple, tuple):
        if len(args) == 2 and args[1] is Ellipsis:
            return {"type": "array", "items": _annotation_to_jsonschema(args[0])}
        return {
            "type": "array",
            "items": [_annotation_to_jsonschema(a) for a in args],
            "minItems": len(args),
            "maxItems": len(args),
        }

    if origin in (dict, dict):
        if len(args) == 2:
            return {
                "type": "object",
                "additionalProperties": _annotation_to_jsonschema(args[1]),
            }
        return {"type": "object"}

    if isinstance(annotation, type):
        if annotation in _PRIMITIVE_TYPES:
            return dict(_PRIMITIVE_TYPES[annotation])

    # Strings inside annotations (PEP-563 future-style) — treat as Any.
    return {}


def _literal_schema(values: tuple[Any, ...]) -> dict[str, Any]:
    """JSON Schema for ``Literal[...]`` — emits ``{"enum": [...]}``.

    Also tags the schema with the underlying primitive type when all
    values share one (e.g. ``Literal["a", "b"]`` → ``{type: "string", enum:...}``).
    """
    out: dict[str, Any] = {"enum": list(values)}
    types_seen = {type(v) for v in values if v is not None}
    if len(types_seen) == 1:
        only = next(iter(types_seen))
        if only in _PRIMITIVE_TYPES:
            out = {**_PRIMITIVE_TYPES[only], **out}
    return out


def _union_schema(args: tuple[Any, ...]) -> dict[str, Any]:
    """JSON Schema for unions.

    * ``X | None`` → schema for ``X`` plus ``"null"`` in the type list
      when expressible, else ``{"anyOf": [..., {"type": "null"}]}``.
    * Mixed primitives like ``int | str`` → ``{"type": ["integer", "string"]}``.
    * Anything more exotic → ``{"anyOf": [...]}``.
    """
    sub_schemas = [_annotation_to_jsonschema(a) for a in args]

    # Common case: all sub-schemas are simple ``{"type": "<name>"}``.
    if all(set(s.keys()) <= {"type"} and isinstance(s.get("type"), str) for s in sub_schemas):
        type_list = sorted({s["type"] for s in sub_schemas})
        if len(type_list) == 1:
            return {"type": type_list[0]}
        return {"type": type_list}

    return {"anyOf": sub_schemas}
