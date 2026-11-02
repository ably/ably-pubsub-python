"""Unit tests for the headers of an HttpPaginatedResponse.

Tests cover:
- HP8: headers as a read-only mapping, looked up by name case-insensitively
"""

import httpx
import pytest

from ably.pubsub.request.paginatedresult import ResponseHeaders


def test_headers_look_up_case_insensitively():
    headers = ResponseHeaders(httpx.Headers({'Content-Type': 'application/json'}))
    assert headers['content-type'] == 'application/json'
    assert headers['CONTENT-TYPE'] == 'application/json'
    assert headers.get('Content-Type') == 'application/json'
    assert 'Content-Type' in headers
    assert 'X-Missing' not in headers
    assert headers.get('X-Missing') is None
    assert 1 not in headers


def test_headers_iterate_as_lower_cased_names():
    headers = ResponseHeaders(httpx.Headers([('X-One', '1'), ('X-Two', '2')]))
    assert list(headers) == ['x-one', 'x-two']
    assert dict(headers.items()) == {'x-one': '1', 'x-two': '2'}
    assert len(headers) == 2


def test_repeated_header_joins_its_values():
    headers = ResponseHeaders(httpx.Headers([('Link', '<a>'), ('Link', '<b>')]))
    assert headers['Link'] == '<a>, <b>'
    assert len(headers) == 1


def test_headers_are_read_only():
    headers = ResponseHeaders(httpx.Headers({'X-One': '1'}))
    with pytest.raises(TypeError):
        headers['X-One'] = '2'
    with pytest.raises(TypeError):
        del headers['X-One']
