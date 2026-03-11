"""
System Skills for Agent Kernel.

This package contains core system skills that provide essential functionality
to the Python Kernel.
"""

from .gateway_callback_skill import GatewayCallbackSkill, get_callback_skill

__all__ = ["GatewayCallbackSkill", "get_callback_skill"]