from loguru import logger
import sys

logger.remove(0)
logger.add(sys.stderr, format="{level} | {message} | {time} | {extra}")
childlogger = logger.bind(seller="test_seller")

logger.info("Hello, this is a test log message from Loguru!")
logger.trace("TRACE MESSAGE")
logger.success("SUCCESS MESSAGE")
logger.debug("DEBUG MESSAGE")
logger.warning("WARNIING MESSAGE")
logger.error("ERROR MESSAAGE")
logger.critical("CRITICAL MESSAGE")
