import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logging():
    """Configures logging for the application."""
    logs_dir = "logs"
    if not os.path.exists(logs_dir):
        try:
            os.makedirs(logs_dir)
        except OSError as e:
            print(f"Warning: Could not create logs directory '{logs_dir}': {e}. Log file may not be created.")
            # Fallback to no file logging if directory creation fails
            pass


    log_file_path = os.path.join(logs_dir, "converter.log")

    # Create a logger
    logger = logging.getLogger("SpotifyYouTubeConverter")
    logger.setLevel(logging.DEBUG) # Set the general level for the logger

    # Prevent duplicate handlers if setup_logging is called multiple times (e.g., in testing or reloads)
    if logger.hasHandlers():
        logger.handlers.clear()

    # Create console handler and set level to INFO
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    
    # Create formatter
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # Create file handler only if logs_dir exists (or was successfully created)
    if os.path.exists(logs_dir):
        # Use RotatingFileHandler for better log management
        fh = RotatingFileHandler(log_file_path, maxBytes=5*1024*1024, backupCount=3) # 5MB per file, 3 backups
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    else:
        logger.warning(f"Log file handler not created because logs directory '{logs_dir}' does not exist.")


    # Configure werkzeug logger for Flask (less verbose for successful requests in console)
    # You might want werkzeug logs in the file for debugging server issues.
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.setLevel(logging.INFO) # Only log warnings and errors for Flask's internal server to console
    if os.path.exists(logs_dir): # Add file handler for werkzeug if logs dir exists
        werkzeug_fh = RotatingFileHandler(os.path.join(logs_dir, "werkzeug.log"), maxBytes=5*1024*1024, backupCount=2)
        werkzeug_fh.setLevel(logging.INFO) # Log INFO and above for werkzeug to its own file
        werkzeug_fh.setFormatter(formatter)
        werkzeug_logger.addHandler(werkzeug_fh)


    return logger

# Initialize logger when this module is imported
app_logger = setup_logging()

if __name__ == '__main__':
    # Example usage:
    test_logger = app_logger # use app_logger directly
    test_logger.debug("This is a debug message for converter.")
    test_logger.info("This is an info message for converter.")
    test_logger.warning("This is a warning message for converter.")
    test_logger.error("This is an error message for converter.")
    test_logger.critical("This is a critical message for converter.")
    
    # Example of Werkzeug logging (will go to werkzeug.log if setup)
    # To see this, you'd typically run a Flask app that uses Werkzeug.
    # For direct testing:
    # werkzeug_logger_instance = logging.getLogger('werkzeug')
    # werkzeug_logger_instance.info("Werkzeug test info log.")
    # werkzeug_logger_instance.error("Werkzeug test error log.")

    print(f"Converter log file should be at: {os.path.abspath(os.path.join('logs', 'converter.log'))}")
    print(f"Werkzeug log file should be at: {os.path.abspath(os.path.join('logs', 'werkzeug.log'))}")