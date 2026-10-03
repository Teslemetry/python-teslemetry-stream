from __future__ import annotations


class TeslemetryStreamError(Exception):
  """Teslemetry Stream Error"""

  message = "An error occurred with the Teslemetry Stream."

  def __init__(self) -> None:
      super().__init__(self.message)


class TeslemetryStreamConnectionError(TeslemetryStreamError):
  """Teslemetry Stream Connection Error"""

  message = "An error occurred with the Teslemetry Stream connection."


class TeslemetryStreamVehicleNotConfigured(TeslemetryStreamError):
  """Teslemetry Stream Not Active Error"""

  message = "This vehicle is not configured to connect to Teslemetry."


class TeslemetryStreamEnded(TeslemetryStreamError):
  """Teslemetry Stream Connection Error"""

  message = "The stream was ended by the server."


class TeslemetryStreamAuthenticationError(TeslemetryStreamError):
  """Teslemetry Stream Authentication Error"""

  message = "The access token was rejected (401/403) and will not be retried."


class TeslemetryStreamBusinessKeyError(TeslemetryStreamError):
  """Teslemetry Stream Business Key Error"""

  message = "This request is not available to a Teslemetry for Business API key."

  def __init__(self, message: str | None = None) -> None:
      if message is not None:
          self.message = message
      super().__init__()
