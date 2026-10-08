from __future__ import annotations

from enum import Enum

from ably.pubsub.types.flags import Flag


class ChannelMode(int, Enum):
    PRESENCE = Flag.PRESENCE
    PUBLISH = Flag.PUBLISH
    SUBSCRIBE = Flag.SUBSCRIBE
    PRESENCE_SUBSCRIBE = Flag.PRESENCE_SUBSCRIBE
    ANNOTATION_PUBLISH = Flag.ANNOTATION_PUBLISH
    ANNOTATION_SUBSCRIBE = Flag.ANNOTATION_SUBSCRIBE


def encode_channel_mode(modes: list[ChannelMode]) -> int:
    """
    Encode a list of ChannelMode values into a bitmask.

    Args:
        modes: List of ChannelMode values to encode

    Returns:
        Integer bitmask with the corresponding flags set
    """
    flags = 0

    for mode in modes:
        flags |= mode.value

    return flags


def decode_channel_mode(flags: int) -> list[ChannelMode]:
    """
    Decode channel mode flags from a bitmask into a list of ChannelMode values.

    Args:
        flags: Integer bitmask containing channel mode flags

    Returns:
        List of ChannelMode values that are set in the flags
    """
    modes = []

    # Check each channel mode flag
    for mode in ChannelMode:
        if flags & mode.value:
            modes.append(mode)

    return modes
