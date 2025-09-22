from __future__ import annotations

from dataclasses import dataclass
from typing import List, TypedDict, NotRequired


class Content(TypedDict, total=False):
    texts: List[str]
    image_prompt: NotRequired[str]
    texts_kana: NotRequired[List[str]]


class Scene(TypedDict, total=False):
    title: str
    image_prompt: NotRequired[str]
    contents: List[Content]
    title_kana: NotRequired[str]


@dataclass
class SubtitleSegment:
    index: int
    start_time: float
    end_time: float
    text: str
    kana_text: str
    segment_type: str = "text"

    def to_srt_format(self) -> str:
        start_time_str = _format_time(self.start_time)
        end_time_str = _format_time(self.end_time)
        return f"{self.index}\n{start_time_str} --> {end_time_str}\n{self.text}\n\n"


def _format_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds_int = int(seconds % 60)
    milliseconds = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds_int:02d},{milliseconds:03d}"

