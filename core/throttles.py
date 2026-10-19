"""
Rate limits for the endpoints that are costly or a target for guessing.
Their rates are set in REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'].
"""
from rest_framework.throttling import SimpleRateThrottle, UserRateThrottle


class AuthRateThrottle(SimpleRateThrottle):
    """
    Signing in, refreshing a token and registering. Counted per client address
    whether or not a login token is sent, so a token cannot be used to get
    around the limit on guessing passwords.
    """

    scope = "auth"

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


class UploadRateThrottle(UserRateThrottle):
    """Uploading or parsing a document, counted per user."""

    scope = "upload"
