"""Service facade with lazy imports.

ASR-only evaluation must not import SQLAlchemy, Redis and every business service merely
to load one independent adapter.
"""
from importlib import import_module


_EXPORTS = {
    "UserService": ("app.services.user_service", "UserService"),
    "MeetingService": ("app.services.meeting_service", "MeetingService"),
    "DocumentService": ("app.services.document_service", "DocumentService"),
    "TodoService": ("app.services.todo_service", "TodoService"),
    "TextProcessService": ("app.services.text_process_service", "TextProcessService"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value
