import base64
import json
import logging
import os
from collections import OrderedDict
from typing import Iterator, Optional
from urllib import parse

import msgpack

from ably.pubsub.http.annotations import HttpAnnotations
from ably.pubsub.request.paginatedresult import PaginatedResult, format_params
from ably.pubsub.types.channeldetails import ChannelDetails
from ably.pubsub.types.message import (
    Message,
    MessageAction,
    MessageVersion,
    make_message_response_handler,
    make_single_message_response_handler,
)
from ably.pubsub.types.operations import MessageOperation, PublishResult, UpdateDeleteResult
from ably.pubsub.types.presence import Presence
from ably.pubsub.util.crypto import get_cipher
from ably.pubsub.util.exceptions import (
    AblyException,
    IncompatibleClientIdException,
    catch_all,
)

log = logging.getLogger(__name__)


class Channel:
    __annotations: HttpAnnotations

    def __init__(self, ably, name, options):
        self.__ably = ably
        self.__name = name
        self.__base_path = '/channels/{}/'.format(parse.quote_plus(name, safe=':'))
        self.__cipher = None
        self.options = options
        self.__presence = Presence(self)
        self.__annotations = HttpAnnotations(self)

    @catch_all
    async def history(self, direction=None, limit: int = None, start=None, end=None):
        """Returns the history for this channel"""
        params = format_params({}, direction=direction, start=start, end=end, limit=limit)
        path = self.__base_path + 'messages' + params

        message_handler = make_message_response_handler(self.__cipher)
        return await PaginatedResult.paginated_query(
            self.ably.http, url=path, response_processor=message_handler)

    def __publish_request_body(self, messages):
        """
        Helper private method, separated from publish() to test RSL1j
        """
        # Idempotent publishing
        if self.ably.options.idempotent_rest_publishing:
            # RSL1k1
            if all(message.id is None for message in messages):
                base_id = base64.b64encode(os.urandom(12)).decode()
                for serial, message in enumerate(messages):
                    message.id = f'{base_id}:{serial}'

        request_body_list = []
        for m in messages:
            if m.client_id == '*':
                raise IncompatibleClientIdException(
                    'Wildcard client_id is reserved and cannot be used when publishing messages',
                    400, 40012)
            elif m.client_id is not None and not self.ably.auth.can_assume_client_id(m.client_id):
                raise IncompatibleClientIdException(
                    f'Cannot publish with client_id \'{m.client_id}\' as it is incompatible with the '
                    f'current configured client_id \'{self.ably.auth.client_id}\'',
                    400, 40012)

            if self.cipher:
                m.encrypt(self.__cipher)

            request_body_list.append(m)

        request_body = [
            message.as_dict(binary=self.ably.options.use_binary_protocol)
            for message in request_body_list]

        if len(request_body) == 1:
            request_body = request_body[0]

        return request_body

    async def _publish(self, arg, *args, **kwargs):
        if isinstance(arg, Message):
            return await self.publish_message(arg, *args, **kwargs)
        elif isinstance(arg, list):
            return await self.publish_messages(arg, *args, **kwargs)
        elif isinstance(arg, str):
            return await self.publish_name_data(arg, *args, **kwargs)
        else:
            raise TypeError(f'Unexpected type {type(arg)}')

    async def publish_message(self, message, params=None, timeout=None):
        return await self.publish_messages([message], params, timeout=timeout)

    async def publish_messages(self, messages, params=None, timeout=None):
        request_body = self.__publish_request_body(messages)
        if not self.ably.options.use_binary_protocol:
            request_body = json.dumps(request_body, separators=(',', ':'))
        else:
            request_body = msgpack.packb(request_body, use_bin_type=True)

        path = self.__base_path + 'messages'
        if params:
            params = {k: str(v).lower() if isinstance(v, bool) else v for k, v in params.items()}
            path += '?' + parse.urlencode(params)
        response = await self.ably.http.post(path, body=request_body, timeout=timeout)

        # Parse response to extract serials
        result_data = response.to_native()
        if result_data and isinstance(result_data, dict):
            return PublishResult.from_dict(result_data)
        return PublishResult()

    async def publish_name_data(self, name, data, timeout=None):
        messages = [Message(name, data)]
        return await self.publish_messages(messages, timeout=timeout)

    async def publish(self, *args, **kwargs):
        """Publishes a message on this channel.

        :Parameters:
        - `name`: the name for this message.
        - `data`: the data for this message.
        - `messages`: list of `Message` objects to be published.
        - `message`: a single `Message` objet to be published

        :attention: You can publish using `name` and `data` OR `messages` OR
        `message`, never all three.
        """
        # For backwards compatibility
        if len(args) == 0:
            if len(kwargs) == 0:
                return await self.publish_name_data(None, None)

            if 'name' in kwargs or 'data' in kwargs:
                name = kwargs.pop('name', None)
                data = kwargs.pop('data', None)
                return await self.publish_name_data(name, data, **kwargs)

            if 'messages' in kwargs:
                messages = kwargs.pop('messages')
                return await self.publish_messages(messages, **kwargs)

        return await self._publish(*args, **kwargs)

    async def status(self):
        """Retrieves current channel active status with no. of publishers, subscribers, presence_members etc"""

        path = f'/channels/{self.name}'
        response = await self.ably.http.get(path)
        obj = response.to_native()
        return ChannelDetails.from_dict(obj)

    async def _send_update(
            self,
            message: Message,
            action: MessageAction,
            operation: Optional[MessageOperation] = None,
            params: Optional[dict] = None,
    ):
        """Internal method to send update/delete/append operations."""
        if not message.serial:
            raise AblyException(
                "Message serial is required for update/delete/append operations",
                status_code=400,
                code=40003,
            )

        if not operation:
            version = None
        else:
            version = MessageVersion(
                client_id=operation.client_id,
                description=operation.description,
                metadata=operation.metadata
            )

        # Create a new message with the operation fields
        update_message = Message(
            name=message.name,
            data=message.data,
            client_id=message.client_id,
            serial=message.serial,
            action=action,
            version=version,
            extras=message.extras,
            annotations=message.annotations,
        )

        # Encrypt if needed
        if self.cipher:
            update_message.encrypt(self.__cipher)

        # Serialize the message
        request_body = update_message.as_dict(binary=self.ably.options.use_binary_protocol)

        if not self.ably.options.use_binary_protocol:
            request_body = json.dumps(request_body, separators=(',', ':'))
        else:
            request_body = msgpack.packb(request_body, use_bin_type=True)

        # Build path with params
        path = self.__base_path + 'messages/{}'.format(parse.quote_plus(message.serial, safe=':'))
        if params:
            params = {k: str(v).lower() if isinstance(v, bool) else v for k, v in params.items()}
            path += '?' + parse.urlencode(params)

        # Send request
        response = await self.ably.http.patch(path, body=request_body)

        # Parse response
        result_data = response.to_native()
        if result_data and isinstance(result_data, dict):
            return UpdateDeleteResult.from_dict(result_data)
        return UpdateDeleteResult()

    async def update_message(self, message: Message, operation: MessageOperation = None, params: dict = None):
        """Updates an existing message on this channel.

        Parameters:
        - message: Message object to update. Must have a serial field.
        - operation: Optional MessageOperation containing description and metadata for the update.
        - params: Optional dict of query parameters.

        Returns:
        - UpdateDeleteResult containing the version serial of the updated message.
        """
        return await self._send_update(message, MessageAction.MESSAGE_UPDATE, operation, params)

    async def delete_message(self, message: Message, operation: MessageOperation = None, params: dict = None):
        """Deletes a message on this channel.

        Parameters:
        - message: Message object to delete. Must have a serial field.
        - operation: Optional MessageOperation containing description and metadata for the delete.
        - params: Optional dict of query parameters.

        Returns:
        - UpdateDeleteResult containing the version serial of the deleted message.
        """
        return await self._send_update(message, MessageAction.MESSAGE_DELETE, operation, params)

    async def append_message(self, message: Message, operation: MessageOperation = None, params: dict = None):
        """Appends data to an existing message on this channel.

        Parameters:
        - message: Message object with data to append. Must have a serial field.
        - operation: Optional MessageOperation containing description and metadata for the append.
        - params: Optional dict of query parameters.

        Returns:
        - UpdateDeleteResult containing the version serial of the appended message.
        """
        return await self._send_update(message, MessageAction.MESSAGE_APPEND, operation, params)

    async def get_message(self, serial_or_message, timeout=None):
        """Retrieves a single message by its serial.

        Parameters:
        - serial_or_message: Either a string serial or a Message object with a serial field.

        Returns:
        - Message object for the requested serial.

        Raises:
        - AblyException: If the serial is missing or the message cannot be retrieved.
        """
        # Extract serial from string or Message object
        if isinstance(serial_or_message, str):
            serial = serial_or_message
        elif isinstance(serial_or_message, Message):
            serial = serial_or_message.serial
        else:
            serial = None

        if not serial:
            raise AblyException(
                'This message lacks a serial. Make sure you have enabled "Message annotations, '
                'updates, and deletes" in channel settings on your dashboard.',
                status_code=400,
                code=40003,
            )

        # Build the path
        path = self.__base_path + 'messages/' + parse.quote_plus(serial, safe=':')

        # Make the request
        response = await self.ably.http.get(path, timeout=timeout)

        # Create Message from the response
        message_handler = make_single_message_response_handler(self.__cipher)
        return message_handler(response)

    async def get_message_versions(self, serial_or_message, params=None):
        """Retrieves version history for a message.

        Parameters:
        - serial_or_message: Either a string serial or a Message object with a serial field.
        - params: Optional dict of query parameters for pagination (e.g., limit, start, end, direction).

        Returns:
        - PaginatedResult containing Message objects representing each version.

        Raises:
        - AblyException: If the serial is missing or versions cannot be retrieved.
        """
        # Extract serial from string or Message object
        if isinstance(serial_or_message, str):
            serial = serial_or_message
        elif isinstance(serial_or_message, Message):
            serial = serial_or_message.serial
        else:
            serial = None

        if not serial:
            raise AblyException(
                'This message lacks a serial. Make sure you have enabled "Message annotations, '
                'updates, and deletes" in channel settings on your dashboard.',
                status_code=400,
                code=40003,
            )

        # Build the path
        params_str = format_params({}, **params) if params else ''
        path = self.__base_path + 'messages/' + parse.quote_plus(serial, safe=':') + '/versions' + params_str

        # Create message handler for decoding
        message_handler = make_message_response_handler(self.__cipher)

        # Return paginated result
        return await PaginatedResult.paginated_query(
            self.ably.http,
            url=path,
            response_processor=message_handler
        )

    @property
    def ably(self):
        return self.__ably

    @property
    def name(self):
        return self.__name

    @property
    def base_path(self):
        return self.__base_path

    @property
    def cipher(self):
        return self.__cipher

    @property
    def options(self):
        return self.__options

    @property
    def presence(self):
        return self.__presence

    @property
    def annotations(self) -> HttpAnnotations:
        return self.__annotations

    @options.setter
    def options(self, options):
        self.__options = options

        if options and 'cipher' in options:
            cipher = options.get('cipher')
            if cipher is not None:
                cipher = get_cipher(cipher)
            self.__cipher = cipher


class Channels:
    def __init__(self, rest):
        self.__ably = rest
        self.__all: dict = OrderedDict()

    def get(self, name, **kwargs):
        if isinstance(name, bytes):
            name = name.decode('ascii')

        if name not in self.__all:
            result = self.__all[name] = Channel(self.__ably, name, kwargs)
        else:
            result = self.__all[name]
            if len(kwargs) != 0:
                result.options = kwargs

        return result

    def __getitem__(self, key):
        return self.get(key)

    def __getattr__(self, name):
        return self.get(name)

    def __contains__(self, item):
        if isinstance(item, Channel):
            name = item.name
        elif isinstance(item, bytes):
            name = item.decode('ascii')
        else:
            name = item

        return name in self.__all

    def __iter__(self) -> Iterator[str]:
        return iter(self.__all.values())

    # RSN4
    def release(self, name: str):
        """Releases a Channel object, deleting it, and enabling it to be garbage collected.
        If the channel does not exist, nothing happens.

        It also removes any listeners associated with the channel.

        Parameters
        ----------
        name: str
            Channel name
        """

        if name not in self.__all:
            return
        del self.__all[name]
