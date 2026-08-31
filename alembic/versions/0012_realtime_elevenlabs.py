"""Canonicalize Realtime agents to OpenAI text output and ElevenLabs TTS.

Revision ID: 0012_realtime_elevenlabs
Revises: 0011_remove_transfer_numbers
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_realtime_elevenlabs"
down_revision: str | None = "0011_remove_transfer_numbers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE agents
            SET realtime_provider = 'openai',
                realtime_model = 'gpt-realtime',
                voice_provider = 'elevenlabs',
                voice_id = CASE
                    WHEN LOWER(COALESCE(tts_provider, voice_provider, '')) = 'elevenlabs'
                         AND NULLIF(voice_id, '') IS NOT NULL
                    THEN voice_id
                    ELSE 'JBFqnCBsd6RMkjVDRZzb'
                END,
                tts_provider = 'elevenlabs',
                tts_model = 'eleven_flash_v2_5',
                stt_provider = NULL,
                stt_model = NULL,
                llm_provider = NULL,
                llm_model = NULL
            WHERE use_realtime IS TRUE
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE agents
            SET realtime_provider = 'openai',
                realtime_model = 'gpt-4o-realtime-preview',
                voice_provider = 'openai',
                voice_id = 'alloy',
                tts_provider = NULL,
                tts_model = NULL
            WHERE use_realtime IS TRUE
            """
        )
    )
