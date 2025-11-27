"""Initial schema for core meeting tables.

Revision ID: 000000000001
Revises: None
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "000000000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("email", sa.String(length=255), nullable=False, unique=True),
            sa.Column("name", sa.String(length=100), nullable=True),
            sa.Column("image_url", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("max_concurrent_bots", sa.Integer(), nullable=False, server_default="1"),
        )
        op.create_index("ix_users_email", "users", ["email"], unique=True)

    if not inspector.has_table("api_tokens"):
        op.create_table(
            "api_tokens",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("token", sa.String(length=255), nullable=False, unique=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_api_tokens_token", "api_tokens", ["token"], unique=True)
        op.create_index("ix_api_tokens_user_id", "api_tokens", ["user_id"])

    if not inspector.has_table("meetings"):
        op.create_table(
            "meetings",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("platform", sa.String(length=100), nullable=False),
            sa.Column("platform_specific_id", sa.String(length=255), nullable=True),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="requested"),
            sa.Column("bot_container_id", sa.String(length=255), nullable=True),
            sa.Column("start_time", sa.DateTime(), nullable=True),
            sa.Column("end_time", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index("ix_meetings_user_id", "meetings", ["user_id"])
        op.create_index("ix_meetings_platform_specific_id", "meetings", ["platform_specific_id"])
        op.create_index(
            "ix_meeting_user_platform_native_id_created_at",
            "meetings",
            ["user_id", "platform", "platform_specific_id", "created_at"],
        )

    if not inspector.has_table("transcriptions"):
        op.create_table(
            "transcriptions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("meeting_id", sa.Integer(), sa.ForeignKey("meetings.id"), nullable=False),
            sa.Column("start_time", sa.Float(), nullable=False),
            sa.Column("end_time", sa.Float(), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("speaker", sa.String(length=255), nullable=True),
            sa.Column("language", sa.String(length=10), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("session_uid", sa.String(length=255), nullable=True),
        )
        op.create_index("ix_transcription_meeting_start", "transcriptions", ["meeting_id", "start_time"])

    if not inspector.has_table("meeting_sessions"):
        op.create_table(
            "meeting_sessions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("meeting_id", sa.Integer(), sa.ForeignKey("meetings.id"), nullable=False),
            sa.Column("session_uid", sa.String(length=255), nullable=False),
            sa.Column(
                "session_start_time",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint("meeting_id", "session_uid", name="_meeting_session_uc"),
        )
        op.create_index("ix_meeting_sessions_meeting_id", "meeting_sessions", ["meeting_id"])
        op.create_index("ix_meeting_sessions_session_uid", "meeting_sessions", ["session_uid"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("meeting_sessions"):
        op.drop_index("ix_meeting_sessions_session_uid", table_name="meeting_sessions")
        op.drop_index("ix_meeting_sessions_meeting_id", table_name="meeting_sessions")
        op.drop_table("meeting_sessions")

    if inspector.has_table("transcriptions"):
        op.drop_index("ix_transcription_meeting_start", table_name="transcriptions")
        op.drop_table("transcriptions")

    if inspector.has_table("meetings"):
        op.drop_index("ix_meeting_user_platform_native_id_created_at", table_name="meetings")
        op.drop_index("ix_meetings_platform_specific_id", table_name="meetings")
        op.drop_index("ix_meetings_user_id", table_name="meetings")
        op.drop_table("meetings")

    if inspector.has_table("api_tokens"):
        op.drop_index("ix_api_tokens_user_id", table_name="api_tokens")
        op.drop_index("ix_api_tokens_token", table_name="api_tokens")
        op.drop_table("api_tokens")

    if inspector.has_table("users"):
        op.drop_index("ix_users_email", table_name="users")
        op.drop_table("users")

