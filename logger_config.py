# ph_config.py

import json
import logging
import logging.handlers as handlers
import sys
import os




def setup_logger(script_name):
	log_dir = f"/home/blackie/bots/ph/logs/{script_name}"
	os.makedirs(log_dir, exist_ok=True)

	###  Define logging system
	logger = logging.getLogger(script_name)
	logger.setLevel(logging.INFO)

	### Define logging formatter
	formatter = logging.Formatter("%(asctime)s - %(message)s", "%Y-%m-%d %I:%M %p")

	## Configure a timed rotating standard log.
	logHandler = handlers.TimedRotatingFileHandler(
		f"{log_dir}/{script_name}_std.log",
		when="midnight",
		interval=1,
		backupCount=2,
	)
	logHandler.setLevel(logging.INFO)
	logHandler.setFormatter(formatter)

	# Configure standard output logging
	stdout_handler = logging.StreamHandler(stream=sys.stdout)
	stdout_handler.setLevel(logging.INFO)
	stdout_handler.setFormatter(formatter)

	# Configure error logging.
	errorLogHandler = handlers.RotatingFileHandler(
		f"{log_dir}/{script_name}_error.log",
		maxBytes=5000,
		backupCount=1,
	)
	errorLogHandler.setLevel(logging.ERROR)
	errorLogHandler.setFormatter(formatter)

	#  Add handlers to loggers
	logger.addHandler(logHandler)
	logger.addHandler(errorLogHandler)
	logger.addHandler(stdout_handler)

	return logger


# Set up logging from notesbot_log_config
script_name = os.path.splitext(os.path.basename(__file__))[0]
logger = setup_logger(script_name)
