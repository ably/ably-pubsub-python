import logging
from enum import IntEnum

from ably.types.mixins import DeltaExtras, EncodeDataMixin
from ably.types.typedbuffer import TypedBuffer
from ably.util.crypto import CipherData
from ably.util.encoding import encode_data
from ably.util.exceptions import AblyException
from ably.util.helper import to_text

log = logging.getLogger(__name__)


class MessageAnnotations:
    """
    Contains information about annotations associated with a particular message.
    """

    def __init__(self, summary=None):
        """
        Args:
            summary: A dict mapping annotation types to their aggregated values.
                    The keys are annotation types (e.g., "reaction:distinct.v1").
                    The values depend on the aggregation method of the annotation type.
        """
        # TM8a: Ensure summary exists
        self.__summary = summary if summary is not None else {}

    @property
    def summary(self):
        """A dict of annotation type to aggregated annotation values."""
        return self.__summary

    def as_dict(self):
        """Convert MessageAnnotations to dictionary format."""
        return {
            'summary': self.summary,
        }

    @staticmethod
    def from_dict(obj):
        """Create MessageAnnotations from dictionary."""
        if obj is None:
            return MessageAnnotations()
        return MessageAnnotations(
            summary=obj.get('summary'),
        )


class MessageVersion:
    """
    Contains the details regarding the current version of the message - including when it was updated and by whom.
    """

    def __init__(self,
                 serial=None,
                 timestamp=None,
                 client_id=None,
                 description=None,
                 metadata=None):
        """
        Args:
            serial: A unique identifier for the version of the message, lexicographically-comparable with other
                   versions (that share the same Message.serial). Will differ from the Message.serial only if the
                   message has been updated or deleted.
            timestamp: The timestamp of the message version. If the Message.action is message.create,
                      this will equal the Message.timestamp.
            client_id: The client ID of the client that updated the message to this version.
            description: The description provided by the client that updated the message to this version.
            metadata: A dict of string key-value pairs that may contain metadata associated with the operation
                     to update the message to this version.
        """
        self.__serial = to_text(serial) if serial is not None else None
        self.__timestamp = timestamp
        self.__client_id = to_text(client_id) if client_id is not None else None
        self.__description = to_text(description) if description is not None else None
        self.__metadata = metadata

    @property
    def serial(self):
        return self.__serial

    @property
    def timestamp(self):
        return self.__timestamp

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
        """Convert MessageVersion to dictionary format."""
        result = {
            'serial': self.serial,
            'timestamp': self.timestamp,
            'clientId': self.client_id,
            'description': self.description,
            'metadata': self.metadata,
        }
        # Remove None values
        return {k: v for k, v in result.items() if v is not None}

    @staticmethod
    def from_dict(obj):
        """Create MessageVersion from dictionary."""
        if obj is None:
            return None
        return MessageVersion(
            serial=obj.get('serial'),
            timestamp=obj.get('timestamp'),
            client_id=obj.get('clientId'),
            description=obj.get('description'),
            metadata=obj.get('metadata'),
        )


class MessageAction(IntEnum):
    """Message action types"""
    MESSAGE_CREATE = 0
    MESSAGE_UPDATE = 1
    MESSAGE_DELETE = 2
    META = 3
    MESSAGE_SUMMARY = 4
    MESSAGE_APPEND = 5


class Message(EncodeDataMixin):

    def __init__(self,
                 name=None,  # TM2g
                 data=None,  # TM2d
                 client_id=None,  # TM2b
                 id=None,  # TM2a
                 connection_id=None,  # TM2c
                 connection_key=None,  # TM2h
                 encoding='',  # TM2e
                 timestamp=None,  # TM2f
                 extras=None,  # TM2i
                 serial=None, # TM2r
                 action=None, # TM2j
                 version=None, # TM2s
                 annotations=None, # TM2t
                 ):

        super().__init__(encoding)

        self.__name = to_text(name)
        self.__data = data
        self.__client_id = to_text(client_id)
        self.__id = to_text(id)
        self.__connection_id = connection_id
        self.__connection_key = connection_key
        self.__timestamp = timestamp
        self.__extras = extras
        self.__serial = serial
        self.__action = action
        self.__version = version
        self.__annotations = annotations

    def __eq__(self, other):
        if isinstance(other, Message):
            return (self.name == other.name
                    and self.data == other.data
                    and self.client_id == other.client_id
                    and self.timestamp == other.timestamp)
        return NotImplemented

    def __ne__(self, other):
        if isinstance(other, Message):
            result = self.__eq__(other)
            if result != NotImplemented:
                return not result
        return NotImplemented

    @property
    def name(self):
        return self.__name

    @property
    def data(self):
        return self.__data

    @property
    def client_id(self):
        return self.__client_id

    @property
    def id(self):
        return self.__id

    @id.setter
    def id(self, value):
        self.__id = value

    @property
    def connection_id(self):
        return self.__connection_id

    @property
    def connection_key(self):
        return self.__connection_key

    @property
    def timestamp(self):
        return self.__timestamp

    @property
    def extras(self):
        return self.__extras

    @property
    def version(self):
        return self.__version

    @property
    def serial(self):
        return self.__serial

    @property
    def action(self):
        return self.__action

    @property
    def annotations(self):
        return self.__annotations

    def encrypt(self, channel_cipher):
        if isinstance(self.data, CipherData):
            return

        elif isinstance(self.data, str):
            self._encoding_array.append('utf-8')

        if isinstance(self.data, dict) or isinstance(self.data, list):
            self._encoding_array.append('json')
            self._encoding_array.append('utf-8')

        typed_data = TypedBuffer.from_obj(self.data)
        if typed_data.buffer is None:
            return True
        encrypted_data = channel_cipher.encrypt(typed_data.buffer)
        self.__data = CipherData(encrypted_data, typed_data.type,
                                 cipher_type=channel_cipher.cipher_type)

    @staticmethod
    def decrypt_data(channel_cipher, data):
        if not isinstance(data, CipherData):
            return
        decrypted_data = channel_cipher.decrypt(data.buffer)
        decrypted_typed_buffer = TypedBuffer(decrypted_data, data.type)

        return decrypted_typed_buffer.decode()

    def decrypt(self, channel_cipher):
        decrypted_data = self.decrypt_data(channel_cipher, self.__data)
        if decrypted_data is not None:
            self.__data = decrypted_data

    def as_dict(self, binary=False):
        request_body = {
            'name': self.name,
            'timestamp': self.timestamp or None,
            'clientId': self.client_id or None,
            'id': self.id or None,
            'connectionId': self.connection_id or None,
            'connectionKey': self.connection_key or None,
            'extras': self.extras,
            'version': self.version.as_dict() if self.version else None,
            'serial': self.serial,
            'action': int(self.action) if self.action is not None else None,
            'annotations': self.annotations.as_dict() if self.annotations else None,
            **encode_data(self.data, self._encoding_array, binary),
        }

        # None values aren't included
        request_body = {k: v for k, v in request_body.items() if v is not None}

        return request_body

    @staticmethod
    def from_encoded(obj, cipher=None, context=None):
        id = obj.get('id')
        name = obj.get('name')
        data = obj.get('data')
        client_id = obj.get('clientId')
        connection_id = obj.get('connectionId')
        timestamp = obj.get('timestamp')
        encoding = obj.get('encoding') or ''
        extras = obj.get('extras', None)
        serial = obj.get('serial')
        action = obj.get('action')
        version = obj.get('version', None)

        delta_extra = DeltaExtras(extras)
        if delta_extra.from_id and delta_extra.from_id != context.last_message_id:
            raise AblyException(f"Delta message decode failure - previous message not available. "
                                f"Message id = {id}", 400, 40018)

        decoded_data = Message.decode(data, encoding, cipher, context)

        if action is not None:
            try:
                action = MessageAction(action)
            except ValueError:
                # If it's not a valid action value, store as None
                action = None
        else:
            action = None

        if version is not None:
            version = MessageVersion.from_dict(version)
        else:
            # TM2s
            version = MessageVersion(serial=serial, timestamp=timestamp)

        # Parse annotations from the wire format
        annotations_obj = obj.get('annotations')
        if annotations_obj is None:
            # TM2u: Always initialize annotations with empty summary
            annotations = MessageAnnotations()
        else:
            annotations = MessageAnnotations.from_dict(annotations_obj)

        # Process annotation summary entries to ensure clipped fields are set
        if annotations and annotations.summary:
            for annotation_type, summary_entry in annotations.summary.items():
                # TM7c1c, TM7d1c: For distinct.v1, unique.v1, multiple.v1
                if (annotation_type.endswith(':distinct.v1') or
                    annotation_type.endswith(':unique.v1') or
                    annotation_type.endswith(':multiple.v1')):
                    # These types have entries that need clipped field
                    if isinstance(summary_entry, dict):
                        for _entry_key, entry_value in summary_entry.items():
                            if isinstance(entry_value, dict) and 'clipped' not in entry_value:
                                entry_value['clipped'] = False
                # TM7c1c: For flag.v1
                elif annotation_type.endswith(':flag.v1'):
                    if isinstance(summary_entry, dict) and 'clipped' not in summary_entry:
                        summary_entry['clipped'] = False

        return Message(
            id=id,
            name=name,
            connection_id=connection_id,
            client_id=client_id,
            timestamp=timestamp,
            extras=extras,
            serial=serial,
            action=action,
            version=version,
            annotations=annotations,
            **decoded_data
        )

    @staticmethod
    def __update_empty_fields(proto_msg: dict, msg: dict, msg_index: int):
        if msg.get("id") is None or msg.get("id") == '':
            msg['id'] = f"{proto_msg.get('id')}:{msg_index}"
        if msg.get("connectionId") is None or msg.get("connectionId") == '':
            msg['connectionId'] = proto_msg.get('connectionId')
        if msg.get("timestamp") is None or msg.get("timestamp") == 0:
            msg['timestamp'] = proto_msg.get('timestamp')

    @staticmethod
    def update_inner_message_fields(proto_msg: dict):
        messages: list[dict] = proto_msg.get('messages')
        presence_messages: list[dict] = proto_msg.get('presence')
        if messages is not None:
            msg_index = 0
            for msg in messages:
                Message.__update_empty_fields(proto_msg, msg, msg_index)
                msg_index = msg_index + 1

        if presence_messages is not None:
            msg_index = 0
            for presence_msg in presence_messages:
                Message.__update_empty_fields(proto_msg, presence_msg, msg_index)
                msg_index = msg_index + 1


def make_message_response_handler(cipher):
    def encrypted_message_response_handler(response):
        messages = response.to_native()
        return Message.from_encoded_array(messages, cipher=cipher)
    return encrypted_message_response_handler

def make_single_message_response_handler(cipher):
    def encrypted_message_response_handler(response):
        message = response.to_native()
        return Message.from_encoded(message, cipher=cipher)
    return encrypted_message_response_handler
