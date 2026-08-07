"""Data models shared by the UI and PDF services."""

from .editable_image import EditableImage, TextAnnotation, render_editable_image

__all__ = ["EditableImage", "TextAnnotation", "render_editable_image"]
