import logging
from pathlib import Path
from datetime import datetime


def setup_logger(log_file: str = "cli.log", level: int = logging.INFO) -> logging.Logger:
    """
    Configure et retourne un logger qui écrit dans un fichier log.
    
    Args:
        log_file: Nom du fichier de log
        level: Niveau de logging
        
    Returns:
        Logger configuré
    """
    logger = logging.getLogger("cli_logger")
    logger.setLevel(level)
    
    # Éviter les doublons de handlers
    if not logger.handlers:
        # Handler fichier
        file_handler = logging.FileHandler(log_file, encoding='utf-8', mode='a')
        file_handler.setLevel(level)
        
        # Format des messages
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
    
    return logger


# Logger global
logger = setup_logger()


def log_info(message: str):
    """Log un message d'information"""
    logger.info(message)


def log_error(message: str):
    """Log un message d'erreur"""
    logger.error(message)


def log_warning(message: str):
    """Log un avertissement"""
    logger.warning(message)


def log_success(message: str):
    """Log un succès (utilisant le niveau INFO)"""
    logger.info(f"✅ SUCCÈS: {message}")


def log_debug(message: str):
    """Log un message de débogage"""
    logger.debug(message)
