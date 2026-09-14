from __future__ import annotations


class ChannelDetails:

    def __init__(self, channel_id, status):
        self.__channel_id = channel_id
        self.__status = status

    @property
    def channel_id(self) -> str:
        return self.__channel_id

    @property
    def status(self) -> ChannelStatus:
        return self.__status

    @staticmethod
    def from_dict(obj):
        kwargs = {
            'channel_id': obj.get("channelId"),
            'status': ChannelStatus.from_dict(obj.get("status"))
        }

        return ChannelDetails(**kwargs)


class ChannelStatus:

    def __init__(self, is_active, occupancy):
        self.__is_active = is_active
        self.__occupancy = occupancy

    @property
    def is_active(self) -> bool:
        return self.__is_active

    @property
    def occupancy(self) -> ChannelOccupancy:
        return self.__occupancy

    @staticmethod
    def from_dict(obj):
        kwargs = {
            'is_active': obj.get("isActive"),
            'occupancy': ChannelOccupancy.from_dict(obj.get("occupancy"))
        }

        return ChannelStatus(**kwargs)


class ChannelOccupancy:

    def __init__(self, metrics):
        self.__metrics = metrics

    @property
    def metrics(self) -> ChannelMetrics:
        return self.__metrics

    @staticmethod
    def from_dict(obj):
        kwargs = {
            'metrics': ChannelMetrics.from_dict(obj.get("metrics"))
        }

        return ChannelOccupancy(**kwargs)


class ChannelMetrics:

    def __init__(self, connections, presence_connections, presence_members,
                 presence_subscribers, publishers, subscribers):
        self.__connections = connections
        self.__presence_connections = presence_connections
        self.__presence_members = presence_members
        self.__presence_subscribers = presence_subscribers
        self.__publishers = publishers
        self.__subscribers = subscribers

    @property
    def connections(self) -> int:
        return self.__connections

    @property
    def presence_connections(self) -> int:
        return self.__presence_connections

    @property
    def presence_members(self) -> int:
        return self.__presence_members

    @property
    def presence_subscribers(self) -> int:
        return self.__presence_subscribers

    @property
    def publishers(self) -> int:
        return self.__publishers

    @property
    def subscribers(self) -> int:
        return self.__subscribers

    @staticmethod
    def from_dict(obj):
        kwargs = {
            'connections': obj.get("connections"),
            'presence_connections': obj.get("presenceConnections"),
            'presence_members': obj.get("presenceMembers"),
            'presence_subscribers': obj.get("presenceSubscribers"),
            'publishers': obj.get("publishers"),
            'subscribers': obj.get("subscribers")
        }

        return ChannelMetrics(**kwargs)
