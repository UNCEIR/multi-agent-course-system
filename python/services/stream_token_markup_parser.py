from __future__ import annotations

import re
from typing import Any, AsyncGenerator


class StreamTokenMarkupParser:
    MARKER_PATTERN = re.compile(
        r"^\[COURSE:([a-zA-Z0-9_-]+):(.+?)\]$", re.IGNORECASE
    )
    MAX_BUFFER = 256

    def __init__(self) -> None:
        self._course_index: int = -1
        self._current_course_id: str | None = None
        self._buffer: str = ""
        self._state: str = "idle"

    async def parse(
        self, token_stream: AsyncGenerator[str, None]
    ) -> AsyncGenerator[dict[str, Any], None]:
        async for chunk in token_stream:
            if not chunk:
                continue

            i = 0
            while i < len(chunk):
                if self._state == "idle":
                    bracket_pos = chunk.find("[", i)
                    if bracket_pos == i:
                        self._buffer = "["
                        self._state = "buffering"
                        i += 1
                    else:
                        end = bracket_pos if bracket_pos != -1 else len(chunk)
                        if i < end:
                            yield {
                                "type": "text",
                                "course_id": self._current_course_id,
                                "token": chunk[i:end],
                            }
                        i = end

                elif self._state == "buffering":
                    if len(self._buffer) >= self.MAX_BUFFER:
                        for event in self._flush_buffer():
                            yield event
                        continue

                    c = chunk[i]
                    self._buffer += c
                    i += 1

                    if c == "[":
                        for event in self._flush_buffer():
                            yield event
                    elif c == "]":
                        match = self.MARKER_PATTERN.match(self._buffer)
                        if match:
                            if self._current_course_id:
                                yield {
                                    "type": "course_end",
                                    "course_id": self._current_course_id,
                                }
                            self._course_index += 1
                            self._current_course_id = match.group(1)
                            yield {
                                "type": "course_start",
                                "course_id": self._current_course_id,
                                "course_name": match.group(2),
                                "index": self._course_index,
                            }
                            self._buffer = ""
                            self._state = "idle"
                        else:
                            for event in self._flush_buffer():
                                yield event

        # stream exhausted
        if self._state == "buffering":
            for event in self._flush_buffer():
                yield event
        if self._current_course_id:
            yield {
                "type": "course_end",
                "course_id": self._current_course_id,
            }

    def _flush_buffer(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        if self._buffer:
            events.append(
                {
                    "type": "text",
                    "course_id": self._current_course_id,
                    "token": self._buffer,
                }
            )
        self._buffer = ""
        self._state = "idle"
        return events
