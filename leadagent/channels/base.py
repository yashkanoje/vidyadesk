from dataclasses import dataclass


@dataclass(frozen=True)
class IncomingMsg:
    institute_id: int
    channel: str  # "telegram" or "whatsapp"
    user_id: str
    msg_id: str  # unique within an institute: "tg:<update id>" or "wa:<message id>"
    text: str | None  # None for voice notes, images, stickers and anything else that is not text
