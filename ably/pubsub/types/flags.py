from enum import Enum


class Flag(int, Enum):
    # Channel attach state flags
    HAS_PRESENCE = 1 << 0
    HAS_BACKLOG = 1 << 1
    RESUMED = 1 << 2
    TRANSIENT = 1 << 4
    ATTACH_RESUME = 1 << 5
    # Channel mode flags
    PRESENCE = 1 << 16
    PUBLISH = 1 << 17
    SUBSCRIBE = 1 << 18
    PRESENCE_SUBSCRIBE = 1 << 19
    ANNOTATION_PUBLISH = 1 << 21
    ANNOTATION_SUBSCRIBE = 1 << 22


def has_flag(message_flags: int, flag: Flag):
    return message_flags & flag > 0
