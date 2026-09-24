import logging
from enum import IntEnum

from ably.types.mixins import EncodeDataMixin
from ably.types.typedbuffer import TypedBuffer
from ably.util.crypto import CipherData
from ably.util.encoding import encode_data
from ably.util.helper import to_text

log = logging.getLogger(__name__)


# Sentinel value to distinguish between "not provided" and "explicitly None"
_UNSET = object()


class AnnotationAction(IntEnum):
    """Annotation action types"""
    ANNOTATION_CREATE = 0
    ANNOTATION_DELETE = 1


class Annotation(EncodeDataMixin):
    """
    Represents an annotation on a message, such as a reaction or other metadata.
    """

    def __init__(self,
                 action=None,
                 serial=None,
                 message_serial=None,
                 type=None,
                 name=None,
                 count=None,
                 data=None,
                 encoding='',
                 id=None,
                 client_id=None,
                 connection_id=None,
                 timestamp=None,
                 extras=None):
        """
        Args:
            action: The action type - either 'annotation.create' or 'annotation.delete'
            serial: A unique identifier for the annotation
            message_serial: The serial of the message this annotation is for
            type: The type of annotation (e.g., 'reaction', 'like', etc.)
            name: The name/value of the annotation (e.g., specific emoji)
            count: Count associated with the annotation
            data: Optional data payload for the annotation
            encoding: Encoding format for the data
            id: (TAN2a) A unique identifier for this annotation
            client_id: The client ID that created this annotation
            connection_id: The connection ID that created this annotation
            timestamp: Timestamp of the annotation
            extras: Additional metadata
        """
        super().__init__(encoding)

        self.__serial = to_text(serial) if serial is not None else None
        self.__message_serial = to_text(message_serial) if message_serial is not None else None
        self.__type = to_text(type) if type is not None else None
        self.__name = to_text(name) if name is not None else None
        self.__action = action if action is not None else AnnotationAction.ANNOTATION_CREATE
        self.__count = count
        self.__data = data
        self.__id = to_text(id) if id is not None else None
        self.__client_id = to_text(client_id) if client_id is not None else None
        self.__connection_id = to_text(connection_id) if connection_id is not None else None
        self.__timestamp = timestamp
        self.__extras = extras
        self.__encoding = encoding

    def __eq__(self, other):
        if isinstance(other, Annotation):
            # TAN2i: serial is the unique identifier for the annotation
            # If both have serials, use serial for comparison
            if self.serial is not None and other.serial is not None:
                return self.serial == other.serial
            # Otherwise fall back to comparing multiple fields
            return (self.message_serial == other.message_serial
                    and self.type == other.type
                    and self.name == other.name
                    and self.action == other.action
                    and self.client_id == other.client_id)
        return NotImplemented

    def __ne__(self, other):
        if isinstance(other, Annotation):
            result = self.__eq__(other)
            if result != NotImplemented:
                return not result
        return NotImplemented

    @property
    def action(self):
        return self.__action

    @property
    def serial(self):
        return self.__serial

    @property
    def message_serial(self):
        return self.__message_serial

    @property
    def type(self):
        return self.__type

    @property
    def name(self):
        return self.__name

    @property
    def count(self):
        return self.__count

    @property
    def data(self):
        return self.__data

    @property
    def client_id(self):
        return self.__client_id

    @property
    def timestamp(self):
        return self.__timestamp

    @property
    def extras(self):
        return self.__extras

    @property
    def id(self):
        return self.__id

    @property
    def connection_id(self):
        return self.__connection_id

    def encrypt(self, channel_cipher):
        """
        Encrypt the annotation's data payload in place.

        Mirrors Message.encrypt(); call before as_dict() when publishing on an
        encrypted channel.
        """
        # Annotations commonly carry no data at all, e.g. a reaction that is fully
        # described by its name, so there is nothing to encrypt.
        if self.__data is None:
            return

        if isinstance(self.__data, CipherData):
            return

        if isinstance(self.__data, str):
            self._encoding_array.append('utf-8')
        elif isinstance(self.__data, (dict, list)):
            self._encoding_array.append('json')
            self._encoding_array.append('utf-8')

        typed_data = TypedBuffer.from_obj(self.__data)
        encrypted_data = channel_cipher.encrypt(typed_data.buffer)
        self.__data = CipherData(encrypted_data, typed_data.type,
                                 cipher_type=channel_cipher.cipher_type)

    def as_dict(self, binary=False):
        """
        Convert annotation to dictionary format for API communication.
        """
        request_body = {
            'action': int(self.action) if self.action is not None else None,
            'serial': self.serial,
            'messageSerial': self.message_serial,
            'type': self.type,  # Annotation type (not data type)
            'name': self.name,
            'count': self.count,
            'id': self.id or None,
            'clientId': self.client_id or None,
            'connectionId': self.connection_id or None,
            'timestamp': self.timestamp or None,
            'extras': self.extras,
            **encode_data(self.data, self._encoding_array, binary)
        }

        # None values aren't included
        request_body = {k: v for k, v in request_body.items() if v is not None}

        return request_body

    @staticmethod
    def from_encoded(obj, cipher=None, context=None):
        """
        Create an Annotation from an encoded object received from the API.

        Args:
            obj: The encoded annotation
            cipher: The channel's cipher, used to decrypt the data payload if it
                    was published on an encrypted channel
            context: Optional decoding context
        """
        action = obj.get('action')
        serial = obj.get('serial')
        message_serial = obj.get('messageSerial')
        type_val = obj.get('type')
        name = obj.get('name')
        count = obj.get('count')
        data = obj.get('data')
        encoding = obj.get('encoding') or ''
        id = obj.get('id')
        client_id = obj.get('clientId')
        connection_id = obj.get('connectionId')
        timestamp = obj.get('timestamp')
        extras = obj.get('extras', None)

        # Decode data if present, passing data=None explicitly when absent
        decoded_data = Annotation.decode(data, encoding, cipher, context) if data is not None else {'data': None}

        # Convert action from int to enum
        if action is not None:
            try:
                action = AnnotationAction(action)
            except ValueError:
                # If it's not a valid action value, store as None
                action = None
        else:
            action = None

        return Annotation(
            action=action,
            serial=serial,
            message_serial=message_serial,
            type=type_val,
            name=name,
            count=count,
            id=id,
            client_id=client_id,
            connection_id=connection_id,
            timestamp=timestamp,
            extras=extras,
            **decoded_data
        )

    @staticmethod
    def from_encoded_array(obj_array, cipher=None, context=None):
        """Create an array of Annotations from encoded objects"""
        return [Annotation.from_encoded(obj, cipher, context) for obj in obj_array]

    @staticmethod
    def from_values(values):
        """Create an Annotation from a dict of values"""
        return Annotation(**values)

    @staticmethod
    def __update_empty_fields(proto_msg: dict, annotation: dict, annotation_index: int):
        """Update empty annotation fields with values from protocol message"""
        if annotation.get("id") is None or annotation.get("id") == '':
            annotation['id'] = f"{proto_msg.get('id')}:{annotation_index}"
        if annotation.get("connectionId") is None or annotation.get("connectionId") == '':
            annotation['connectionId'] = proto_msg.get('connectionId')
        if annotation.get("timestamp") is None or annotation.get("timestamp") == 0:
            annotation['timestamp'] = proto_msg.get('timestamp')

    @staticmethod
    def update_inner_annotation_fields(proto_msg: dict):
        """
        Update inner annotation fields with protocol message data (RTAN4b).

        Populates empty id, connectionId, and timestamp fields in annotations
        from the protocol message values.
        """
        annotations: list[dict] = proto_msg.get('annotations')
        if annotations is not None:
            for annotation_index, annotation in enumerate(annotations):
                Annotation.__update_empty_fields(proto_msg, annotation, annotation_index)

    def __str__(self):
        return (
            f"Annotation(action={self.action}, messageSerial={self.message_serial}, "
            f"type={self.type}, name={self.name})"
        )

    def __repr__(self):
        return self.__str__()

    def _copy_with(self,
                  action=_UNSET,
                  serial=_UNSET,
                  message_serial=_UNSET,
                  type=_UNSET,
                  name=_UNSET,
                  count=_UNSET,
                  data=_UNSET,
                  encoding=_UNSET,
                  id=_UNSET,
                  client_id=_UNSET,
                  connection_id=_UNSET,
                  timestamp=_UNSET,
                  extras=_UNSET):
        """
        Create a copy of this Annotation with optionally modified fields.

        To explicitly set a field to None, pass None as the value.
        Fields not provided will retain their original values.

        Args:
            action: Override the action type (or None to clear it)
            serial: Override the serial (or None to clear it)
            message_serial: Override the message serial (or None to clear it)
            type: Override the type (or None to clear it)
            name: Override the name (or None to clear it)
            count: Override the count (or None to clear it)
            data: Override the data payload (or None to clear it)
            encoding: Override the encoding format (or None to clear it)
            id: Override the ID (or None to clear it)
            client_id: Override the client ID (or None to clear it)
            connection_id: Override the connection ID (or None to clear it)
            timestamp: Override the timestamp (or None to clear it)
            extras: Override the extras metadata (or None to clear it)

        Returns:
            A new Annotation instance with the specified fields updated

        Example:
            # Keep existing name, change type
            new_ann = annotation.copy_with(type="like")

            # Explicitly set name to None
            new_ann = annotation.copy_with(name=None)
        """
        # Get encoding from the mixin's property
        return Annotation(
            action=self.__action if action is _UNSET else action,
            serial=self.__serial if serial is _UNSET else serial,
            message_serial=self.__message_serial if message_serial is _UNSET else message_serial,
            type=self.__type if type is _UNSET else type,
            name=self.__name if name is _UNSET else name,
            count=self.__count if count is _UNSET else count,
            data=self.__data if data is _UNSET else data,
            encoding=self.__encoding if encoding is _UNSET else encoding,
            id=self.__id if id is _UNSET else id,
            client_id=self.__client_id if client_id is _UNSET else client_id,
            connection_id=self.__connection_id if connection_id is _UNSET else connection_id,
            timestamp=self.__timestamp if timestamp is _UNSET else timestamp,
            extras=self.__extras if extras is _UNSET else extras,
        )


def make_annotation_response_handler(cipher=None):
    """Create a response handler for annotation API responses"""
    def annotation_response_handler(response):
        annotations = response.to_native()
        return Annotation.from_encoded_array(annotations, cipher=cipher)
    return annotation_response_handler


def make_single_annotation_response_handler(cipher=None):
    """Create a response handler for single annotation API responses"""
    def single_annotation_response_handler(response):
        annotation = response.to_native()
        return Annotation.from_encoded(annotation, cipher=cipher)
    return single_annotation_response_handler
