from dataclasses import dataclass


@dataclass()
class ConnectionDetails:
    connection_state_ttl: int
    max_idle_interval: int
    connection_key: str

    def __init__(self, connection_state_ttl: int, max_idle_interval: int,
                 connection_key: str, client_id: str, site_code: str = None,
                 objects_gc_grace_period: int = None):
        self.connection_state_ttl = connection_state_ttl
        self.max_idle_interval = max_idle_interval
        self.connection_key = connection_key
        self.client_id = client_id
        # CD2j: the site the connection reached, under which LiveObjects applies its own operations
        self.site_code = site_code
        # CD2i: how long tombstoned objects and map entries are kept before release, in milliseconds
        self.objects_gc_grace_period = objects_gc_grace_period

    @staticmethod
    def from_dict(json_dict: dict):
        return ConnectionDetails(json_dict.get('connectionStateTtl'), json_dict.get('maxIdleInterval'),
                                 json_dict.get('connectionKey'), json_dict.get('clientId'),
                                 json_dict.get('siteCode'), json_dict.get('objectsGCGracePeriod'))
