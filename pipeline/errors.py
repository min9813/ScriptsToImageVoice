from __future__ import annotations

class PipelineError(Exception):
    """Base error for the ScriptsToImageVoice pipeline."""


class VoicevoxError(PipelineError):
    """Raised when a VOICEVOX API call fails."""


class AudioSynthesisError(PipelineError):
    """Raised when audio synthesis or WAV handling fails."""


class SubtitleGenerationError(PipelineError):
    """Raised when subtitle segments or SRT generation fails."""


class SubJsonNotFoundError(PipelineError, FileNotFoundError):
    """Raised when expected sub.json or project directory is not found."""

