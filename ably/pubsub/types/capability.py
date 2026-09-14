import json
import logging
from collections.abc import MutableMapping
from typing import Optional, Union

log = logging.getLogger(__name__)


class Capability(MutableMapping):
    def __init__(self, capability: Optional[Union[dict, str]] = None):
        # RSA9f: provided capability can be a JSON string
        if capability and isinstance(capability, str):
            try:
                capability = json.loads(capability)
            except json.JSONDecodeError:
                capability = json.loads(capability.replace("'", '"'))

        if capability is None:
            capability = {}

        self.__dict = dict(capability)
        for k, v in capability.items():
            self[k] = v

    def __eq__(self, other):
        if isinstance(other, Capability):
            return Capability.c14n(self) == Capability.c14n(other)
        return NotImplemented

    def __ne__(self, other):
        if isinstance(other, Capability):
            return Capability.c14n(self) != Capability.c14n(other)
        return NotImplemented

    def __getitem__(self, key):
        return self.__dict[key]

    def __iter__(self):
        return iter(self.__dict)

    def __len__(self):
        return len(self.__dict)

    def __contains__(self, key):
        return key in self.__dict

    def __setitem__(self, key, value):
        # validate that the value is a list of ops and that the key is a string
        if not isinstance(key, str):
            raise ValueError('Capability keys must be strings')

        if isinstance(value, str):
            value = [value]

        operations = set()
        for val in iter(value):
            if not isinstance(val, str):
                raise ValueError('Operations must be strings')
            operations.add(val)

        self.__dict[key] = operations

    def __delitem__(self, key):
        del self.__dict[key]

    def setdefault(self, key, default):
        if key not in self:
            self[key] = default
        return self[key]

    def add_resource(self, resource, operations=None):
        if operations is None:
            operations = []
        if isinstance(operations, str):
            operations = [operations]
        self[resource] = list(operations)

    def add_operation_to_resource(self, operation, resource):
        self.setdefault(resource, []).append(operation)

    def __str__(self):
        return Capability.c14n(self)

    def to_dict(self):
        return {k: sorted(v) for k, v in self.items()}

    @staticmethod
    def c14n(capability):
        sorted_ops = capability.to_dict()
        return json.dumps(sorted_ops, sort_keys=True)
