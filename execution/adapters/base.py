"""
execution/adapters/base.py — Base Broker Adapter Architecture.

Provides shared connectivity state management, logging, credential verification,
and health-check hooks for concrete broker implementations.
"""

from __future__ import annotations

import logging
from abc import abstractmethod
from typing import Any, Dict, List, Optional
from execution.broker import Broker
from execution.exceptions import (
    BrokerAuthenticationError,
    BrokerConnectionError,
    BrokerError,
)

from execution.models import (
    BrokerCapabilities,
    BrokerConnectionState,
    OrderStatus,
    PaperAccount,
    PaperFill,
    PaperOrder,
    PaperPosition,
)

logger = logging.getLogger(__name__)


class BaseBrokerAdapter(Broker):
    """
    Abstract base adapter for external broker APIs.
    
    Manages connection state transitions, authentication lifecycle,
    and capability introspection.
    """

    def __init__(self, broker_name: str, config: Optional[Dict[str, Any]] = None):
        self.broker_name: str = broker_name
        self.config: Dict[str, Any] = config or {}
        self.connection_state: BrokerConnectionState = BrokerConnectionState.DISCONNECTED
        self._last_heartbeat: Optional[str] = None

    def connect(self) -> bool:
        """Establish session or validate credentials with the broker API."""
        try:
            self.connection_state = BrokerConnectionState.CONNECTING
            success = self._perform_connect()
            if success:
                self.connection_state = BrokerConnectionState.CONNECTED
                logger.info(f"[{self.broker_name}] Successfully connected.")
                return True
            else:
                self.connection_state = BrokerConnectionState.ERROR
                logger.error(f"[{self.broker_name}] Connection attempt failed.")
                return False
        except (BrokerAuthenticationError, BrokerConnectionError):
            self.connection_state = BrokerConnectionState.ERROR
            raise
        except Exception as e:
            self.connection_state = BrokerConnectionState.ERROR
            raise BrokerConnectionError(f"Connection failed: {e}", broker_name=self.broker_name) from e


    def disconnect(self) -> None:
        """Terminate connection or invalidate session tokens."""
        self._perform_disconnect()
        self.connection_state = BrokerConnectionState.DISCONNECTED
        logger.info(f"[{self.broker_name}] Disconnected.")

    def get_connection_status(self) -> BrokerConnectionState:
        """Return current connection state."""
        return self.connection_state

    def is_connected(self) -> bool:
        """Check if currently connected."""
        return self.connection_state == BrokerConnectionState.CONNECTED

    @abstractmethod
    def _perform_connect(self) -> bool:
        """Subclass implementation of broker authentication/connect handshake."""
        pass

    @abstractmethod
    def _perform_disconnect(self) -> None:
        """Subclass implementation of disconnect / session cleanup."""
        pass
