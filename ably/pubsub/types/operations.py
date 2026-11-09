class MessageOperation:
    """Metadata for message update/delete/append operations."""

    def __init__(self, client_id=None, description=None, metadata=None):
        """
        Args:
            description: Optional description of the operation.
            metadata: Optional dict of metadata key-value pairs associated with the operation.
        """
        self.__client_id = client_id
        self.__description = description
        self.__metadata = metadata

    @property
    def client_id(self):
        return self.__client_id

    @property
    def description(self):
        return self.__description

    @property
    def metadata(self):
        return self.__metadata

    def as_dict(self):
        """Convert MessageOperation to dictionary format."""
        result = {
            'clientId': self.client_id,
            'description': self.description,
            'metadata': self.metadata,
        }
        # Remove None values
        return {k: v for k, v in result.items() if v is not None}

    @staticmethod
    def from_dict(obj):
        """Create MessageOperation from dictionary."""
        if obj is None:
            return None
        return MessageOperation(
            client_id=obj.get('clientId'),
            description=obj.get('description'),
            metadata=obj.get('metadata'),
        )


class PublishResult:
    """Result of a publish operation containing message serials."""

    def __init__(self, serials=None):
        """
        Args:
            serials: List of message serials (strings or None) in 1:1 correspondence with published messages.
        """
        self.__serials = serials or []

    @property
    def serials(self):
        return self.__serials

    @staticmethod
    def from_dict(obj):
        """Create PublishResult from dictionary."""
        if obj is None:
            return PublishResult()
        return PublishResult(serials=obj.get('serials', []))


class UpdateDeleteResult:
    """Result of an update or delete operation containing version serial."""

    def __init__(self, version_serial=None):
        """
        Args:
            version_serial: The serial of the resulting message version after the operation.
        """
        self.__version_serial = version_serial

    @property
    def version_serial(self):
        return self.__version_serial

    @staticmethod
    def from_dict(obj):
        """Create UpdateDeleteResult from dictionary."""
        if obj is None:
            return UpdateDeleteResult()
        return UpdateDeleteResult(version_serial=obj.get('versionSerial'))
