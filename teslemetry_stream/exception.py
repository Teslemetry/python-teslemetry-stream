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
