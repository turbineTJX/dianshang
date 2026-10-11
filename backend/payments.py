"""Payment gateways are separate from the credit ledger and model adapters."""
from abc import ABC, abstractmethod
from fastapi import HTTPException


class PaymentGateway(ABC):
    @abstractmethod
    def create_checkout(self, order_id: str, amount_cents: int) -> dict:
        pass

    @abstractmethod
    def verify_webhook(self, headers: dict, raw_body: bytes) -> dict:
        """Return verified order ID, transaction ID and paid amount. Never trust browser callbacks."""


class UnconfiguredGateway(PaymentGateway):
    def create_checkout(self, order_id, amount_cents):
        raise HTTPException(503, '支付渠道尚未配置，当前不能在线充值。管理员可在成员管理中发放测试积分。')

    def verify_webhook(self, headers, raw_body):
        raise HTTPException(503, '支付渠道尚未配置')


gateway: PaymentGateway = UnconfiguredGateway()
