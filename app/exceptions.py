# app/exceptions.py

class AppException(Exception):
    """Base exception for app"""
    pass


class AgentException(AppException):
    """Raised when agent pipeline fails"""
    pass


class KnowledgeBaseException(AppException):
    """Raised when knowledge base / vector store fails"""
    pass
