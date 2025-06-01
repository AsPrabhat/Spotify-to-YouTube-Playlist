import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logging():
    """
    Configures the application's logging system.

    Sets up console and file handlers for the main application logger and a
    separate file handler for the Werkzeug (Flask) logger.
    Log files are stored in the 'logs' directory.
    """
    logs_dir = "logs"
    # Create logs directory if it doesn't exist
    if not os.path.exists(logs_dir):
        try:
            os.makedirs(logs_dir)
        except OSError as e:
            print(f"Warning: Could not create logs directory '{logs_dir}': {e}. Log file may not be created.")
            pass

    log_file_path = os.path.join(logs_dir, "converter.log")

    logger = logging.getLogger("SpotifyYouTubeConverter")
    logger.setLevel(logging.DEBUG)

    # Clear existing handlers to prevent duplicate logs in reloads (e.g., Flask debug mode)
    if logger.hasHandlers():
        logger.handlers.clear()

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # File handler for application logs
    if os.path.exists(logs_dir):
        fh = RotatingFileHandler(log_file_path, maxBytes=5*1024*1024, backupCount=3)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    else:
        logger.warning(f"Log file handler not created because logs directory '{logs_dir}' does not exist.")

    # Configure Werkzeug logger (Flask's internal logger)
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.setLevel(logging.INFO)
    if os.path.exists(logs_dir):
        werkzeug_fh = RotatingFileHandler(os.path.join(logs_dir, "werkzeug.log"), maxBytes=5*1024*1024, backupCount=2)
        werkzeug_fh.setLevel(logging.INFO)
        werkzeug_fh.setFormatter(formatter)
        werkzeug_logger.addHandler(werkzeug_fh)

    return logger

# Initialize the application logger
app_logger = setup_logging()

if __name__ == '__main__':
    # Test logging functionality when run directly
    test_logger = app_logger
    test_logger.debug("This is a debug message for converter.")
    test_logger.info("This is an info message for converter.")
    test_logger.warning("This is a warning message for converter.")
    test_logger.error("This is an error message for converter.")
    test_logger.critical("This is a critical message for converter.")

    print(f"Converter log file should be at: {os.path.abspath(os.path.join('logs', 'converter.log'))}")
    print(f"Werkzeug log file should be at: {os.path.abspath(os.path.join('logs', 'werkzeug.log'))}")
