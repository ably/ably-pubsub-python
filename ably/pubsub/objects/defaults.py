"""Default values for the LiveObjects client."""

# RTO10a: how often tombstoned objects and map entries are checked for release
GC_INTERVAL_MS = 5 * 60 * 1000

# RTO10b3: the grace period used when ConnectionDetails.objectsGCGracePeriod is absent
GC_GRACE_PERIOD_MS = 24 * 60 * 60 * 1000

# RTO3b: the object id of the root map, which every ObjectsPool holds
ROOT_OBJECT_ID = 'root'
