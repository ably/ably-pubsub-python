class PushApnsBroadcast:
    """An APNs broadcast channel created for an iOS Live Activity.

    Experimental: this is a preview feature and may change in a future non-major release.
    """

    def __init__(self, id, apns_channel_id):
        self.__id = id
        self.__apns_channel_id = apns_channel_id

    @property
    def id(self):
        """The opaque Ably broadcast id, passed to the `push.admin.live_activity` methods."""
        return self.__id

    @property
    def apns_channel_id(self):
        """The Apple-assigned channel id."""
        return self.__apns_channel_id

    @classmethod
    def from_dict(cls, obj):
        return cls(id=obj.get('id'), apns_channel_id=obj.get('apnsChannelId'))
