"""Typed application errors.

The ErrorCode enum and its mapping to run statuses (plan section 5.7) arrive in T0.3.
"""


class AIReviewerError(Exception):
    """Base class for all application errors."""


class ConfigError(AIReviewerError):
    """Missing or invalid configuration at startup.

    Not a run outcome, so it has no section 5.7 error code. Messages name environment
    variables, never their values.
    """
