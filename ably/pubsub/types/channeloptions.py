from __future__ import annotations

from typing import Any

from ably.pubsub.types.channelmode import ChannelMode
from ably.pubsub.util.crypto import CipherParams
from ably.pubsub.util.exceptions import AblyException


class ChannelOptions:
    """Channel options for Ably Realtime channels

    Attributes
    ----------
    cipher : CipherParams, optional
        Requests encryption for this channel when not null, and specifies encryption-related parameters.
    params : Dict[str, str], optional
        Channel parameters that configure the behavior of the channel.
    """

    def __init__(
        self,
        cipher: CipherParams | None = None,
        params: dict | None = None,
        modes: list[ChannelMode] | None = None
    ):
        self.__cipher = cipher
        self.__params = params
        self.__modes = modes
        # Validate params
        if self.__params and not isinstance(self.__params, dict):
            raise AblyException("params must be a dictionary", 40000, 400)

    @property
    def cipher(self) -> CipherParams | None:
        """Get cipher configuration"""
        return self.__cipher

    @property
    def params(self) -> dict[str, str] | None:
        """Get channel parameters"""
        return self.__params

    @property
    def modes(self) -> list[ChannelMode] | None:
        """Get channel modes"""
        return self.__modes

    def __eq__(self, other):
        """Check equality with another ChannelOptions instance"""
        if not isinstance(other, ChannelOptions):
            return False

        return (self.__cipher == other.__cipher and
                self.__params == other.__params and self.__modes == other.__modes)

    def __hash__(self):
        """Make ChannelOptions hashable"""
        return hash((
            self.__cipher,
            tuple(sorted(self.__params.items())) if self.__params else None,
            tuple(sorted(self.__modes)) if self.__modes else None
        ))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation"""
        result = {}
        if self.__cipher is not None:
            result['cipher'] = self.__cipher
        if self.__params:
            result['params'] = self.__params
        if self.__modes:
            result['modes'] = self.__modes
        return result

    @classmethod
    def from_dict(cls, options_dict: dict[str, Any]) -> ChannelOptions:
        """Create ChannelOptions from dictionary"""
        if not isinstance(options_dict, dict):
            raise AblyException("options must be a dictionary", 40000, 400)

        return cls(
            cipher=options_dict.get('cipher'),
            params=options_dict.get('params'),
            modes=options_dict.get('modes'),
        )
