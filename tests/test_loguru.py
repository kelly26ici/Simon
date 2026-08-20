from loguru import logger
import sys

def test_loguru_levels_emitted():
    """Verify loguru level emissions and binding."""
    childlogger = logger.bind(seller="test_seller")
    childlogger.info("Hello, this is a test log message from Loguru!")
    childlogger.trace("TRACE MESSAGE")
    childlogger.success("SUCCESS MESSAGE")
    childlogger.debug("DEBUG MESSAGE")
    childlogger.warning("WARNING MESSAGE")
    childlogger.error("ERROR MESSAGE")
    childlogger.critical("CRITICAL MESSAGE")

