"""Small shared types for the window code (kept apart to avoid import loops)."""

from dataclasses import dataclass

from mosign.draw import Rect


@dataclass
class Button:
    command: str
    label: str
    key: str
    rect: Rect = None
