from __future__ import annotations

import base64
import json
import logging
import os
from urllib import parse

import msgpack

from ably.pubsub.http.paginatedresult import PaginatedResult, format_params
from ably.pubsub.types.annotation import (
    Annotation,
    AnnotationAction,
    make_annotation_response_handler,
)
from ably.pubsub.types.message import Message
from ably.pubsub.types.options import Options
from ably.pubsub.util.exceptions import AblyException

log = logging.getLogger(__name__)


def serial_from_msg_or_serial(msg_or_serial):
    """
    Extract the message serial from either a string serial or a Message object.

    Args:
        msg_or_serial: Either a string serial or a Message object with a serial property

    Returns:
        str: The message serial

    Raises:
        AblyException: If the input is invalid or serial is missing
    """
    if isinstance(msg_or_serial, str):
        message_serial = msg_or_serial
    elif isinstance(msg_or_serial, Message):
        message_serial = msg_or_serial.serial
    else:
        message_serial = None

    if not message_serial or not isinstance(message_serial, str):
        raise AblyException(
            message='First argument of annotations.publish() must be either a Message '
            'or a message serial (string)',
            status_code=400,
            code=40003,
        )

    return message_serial


def construct_validate_annotation(msg_or_serial, annotation: Annotation) -> Annotation:
    """
    Construct and validate an Annotation from input values.

    Args:
        msg_or_serial: Either a string serial or a Message object
        annotation: Annotation object

    Returns:
        Annotation: The constructed annotation

    Raises:
        AblyException: If the inputs are invalid
    """
    message_serial = serial_from_msg_or_serial(msg_or_serial)

    if not annotation or not isinstance(annotation, Annotation):
        raise AblyException(
            message='Second argument of annotations.publish() must be an Annotation '
            '(the intended annotation to publish)',
            status_code=400,
            code=40003,
        )

    # RSAN1a3: Validate that annotation type is specified
    if not annotation.type:
        raise AblyException(
            message='Annotation type must be specified',
            status_code=400,
            code=40000,
        )

    return annotation._copy_with(
        message_serial=message_serial,
    )


class RestAnnotations:
    """
    Provides REST API methods for managing annotations on messages.
    """

    __client_options: Options

    def __init__(self, channel):
        """
        Initialize RestAnnotations.

        Args:
            channel: The REST Channel this annotations instance belongs to
        """
        self.__channel = channel
        self.__client_options = channel.ably.options

    def __base_path_for_serial(self, serial):
        """
        Build the base API path for a message serial's annotations.

        Args:
            serial: The message serial

        Returns:
            str: The API path
        """
        channel_path = '/channels/{}/'.format(parse.quote_plus(self.__channel.name, safe=':'))
        return channel_path + 'messages/' + parse.quote_plus(serial, safe=':') + '/annotations'

    async def __send_annotation(self, annotation: Annotation, params: dict | None = None):
        """
        Internal method to send an annotation to the API.

        Args:
            annotation: Validated Annotation object with action and message_serial set
            params: Optional dict of query parameters
        """
        # RSAN1c4: Generate random ID if not provided (for idempotent publishing)
        # Spec: base64-encode at least 9 random bytes, append ':0'
        if not annotation.id and self.__client_options.idempotent_rest_publishing:
            random_id = base64.b64encode(os.urandom(9)).decode('ascii') + ':0'
            annotation = annotation._copy_with(id=random_id)

        # RSAN1c3: encrypt the data payload on an encrypted channel
        if self.__channel.cipher:
            annotation.encrypt(self.__channel.cipher)

        # Convert to wire format
        request_body = annotation.as_dict(binary=self.__channel.ably.options.use_binary_protocol)

        # Wrap in array as API expects array of annotations
        request_body = [request_body]

        # Encode based on protocol
        if not self.__channel.ably.options.use_binary_protocol:
            request_body = json.dumps(request_body, separators=(',', ':'))
        else:
            request_body = msgpack.packb(request_body, use_bin_type=True)

        # Build path
        path = self.__base_path_for_serial(annotation.message_serial)
        if params:
            params = {k: str(v).lower() if isinstance(v, bool) else v for k, v in params.items()}
            path += '?' + parse.urlencode(params)

        # Send request
        await self.__channel.ably.http.post(path, body=request_body)

    async def publish(
        self,
        msg_or_serial,
        annotation: Annotation,
        params: dict | None = None,
    ):
        """
        Publish an annotation on a message.

        Args:
            msg_or_serial: Either a message serial (string) or a Message object
            annotation: Annotation object
            params: Optional dict of query parameters

        Returns:
            None

        Raises:
            AblyException: If the request fails or inputs are invalid
        """
        annotation = construct_validate_annotation(msg_or_serial, annotation)

        # RSAN1c1: Explicitly set action to ANNOTATION_CREATE
        annotation = annotation._copy_with(action=AnnotationAction.ANNOTATION_CREATE)

        await self.__send_annotation(annotation, params)

    async def delete(
        self,
        msg_or_serial,
        annotation: Annotation,
        params: dict | None = None,
    ):
        """
        Delete an annotation on a message.

        This is a convenience method that sets the action to 'annotation.delete'
        and calls publish().

        Args:
            msg_or_serial: Either a message serial (string) or a Message object
            annotation: Annotation object
            params: Optional dict of query parameters

        Returns:
            None

        Raises:
            AblyException: If the request fails or inputs are invalid
        """
        annotation = construct_validate_annotation(msg_or_serial, annotation)

        # RSAN2a: Explicitly set action to ANNOTATION_DELETE
        annotation = annotation._copy_with(action=AnnotationAction.ANNOTATION_DELETE)

        return await self.__send_annotation(annotation, params)

    async def get(self, msg_or_serial, params: dict | None = None):
        """
        Retrieve annotations for a message with pagination support.

        Args:
            msg_or_serial: Either a message serial (string) or a Message object
            params: Optional dict of query parameters (limit, start, end, direction)

        Returns:
            PaginatedResult: A paginated result containing Annotation objects

        Raises:
            AblyException: If the request fails or serial is invalid
        """
        message_serial = serial_from_msg_or_serial(msg_or_serial)

        # Build path
        params_str = format_params({}, **params) if params else ''
        path = self.__base_path_for_serial(message_serial) + params_str

        # Create annotation response handler
        annotation_handler = make_annotation_response_handler(cipher=self.__channel.cipher)

        # Return paginated result
        return await PaginatedResult.paginated_query(
            self.__channel.ably.http,
            url=path,
            response_processor=annotation_handler
        )
