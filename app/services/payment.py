from dataclasses import dataclass
from urllib.parse import quote
import aiohttp
from app.config import get_settings

@dataclass
class PaymentResult:
    success: bool
    authority: str | None = None
    reference_id: str | None = None
    payment_url: str | None = None
    message: str = ''


def toman_to_irr(amount: int) -> int:
    return int(amount) * 10


def relay_url(authority: str) -> str:
    """Our own /pay/ hand-off page: ZarinPal only admits visitors referred by the merchant's registered domain."""
    base=get_settings().public_base_url.rstrip('/')
    return f"{base}/pay/{quote(authority, safe='')}" if base else ''

class ZarinpalGateway:
    REQUEST_URL = 'https://payment.zarinpal.com/pg/v4/payment/request.json'
    VERIFY_URL = 'https://payment.zarinpal.com/pg/v4/payment/verify.json'
    START_URL = 'https://www.zarinpal.com/pg/StartPay/{authority}'
    SANDBOX_REQUEST_URL = 'https://sandbox.zarinpal.com/pg/v4/payment/request.json'
    SANDBOX_VERIFY_URL = 'https://sandbox.zarinpal.com/pg/v4/payment/verify.json'
    SANDBOX_START_URL = 'https://sandbox.zarinpal.com/pg/StartPay/{authority}'
    def __init__(self):
        s=get_settings(); self.merchant_id=s.zarinpal_merchant_id; self.callback=s.resolved_zarinpal_callback
        if s.zarinpal_sandbox:
            self.REQUEST_URL,self.VERIFY_URL,self.START_URL=self.SANDBOX_REQUEST_URL,self.SANDBOX_VERIFY_URL,self.SANDBOX_START_URL
    async def create(self, order_id:int, amount:int, description:str)->PaymentResult:
        if not self.merchant_id or not self.callback: raise RuntimeError('Zarinpal is not configured')
        payload={'merchant_id':self.merchant_id,'amount':toman_to_irr(amount),'description':description[:250],'callback_url':self.callback,'metadata':{'order_id':str(order_id)}}
        timeout=aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.post(self.REQUEST_URL,json=payload) as r:
                data=await r.json(content_type=None)
        if r.status != 200 or not data.get('data') or data['data'].get('code') != 100 or not data['data'].get('authority'):
            return PaymentResult(False,message=str(data.get('errors') or data))
        auth=data['data']['authority']; return PaymentResult(True,authority=auth,payment_url=relay_url(auth) or self.start_url(auth))
    def start_url(self, authority:str)->str:
        return self.START_URL.format(authority=quote(authority, safe=''))
    async def verify(self, authority:str, amount:int)->PaymentResult:
        if not self.merchant_id: raise RuntimeError('Zarinpal is not configured')
        payload={'merchant_id':self.merchant_id,'amount':toman_to_irr(amount),'authority':authority}
        timeout=aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.post(self.VERIFY_URL,json=payload) as r:
                data=await r.json(content_type=None)
        code=(data.get('data') or {}).get('code')
        if r.status == 200 and code in (100,101):
            ref=str((data.get('data') or {}).get('ref_id') or authority)
            return PaymentResult(True,reference_id=ref,message='verified')
        return PaymentResult(False,message=str(data.get('errors') or data))

class PaymentService:
    def __init__(self): self.settings=get_settings()
    async def create_zarinpal(self, order_id:int, amount:int, description:str):
        if self.settings.payment_mode.lower() not in ('zarinpal','both'): raise RuntimeError('Zarinpal payment is disabled')
        return await ZarinpalGateway().create(order_id,amount,description)
    async def verify_zarinpal(self, authority:str, amount:int):
        if self.settings.payment_mode.lower() not in ('zarinpal','both'): raise RuntimeError('Zarinpal payment is disabled')
        return await ZarinpalGateway().verify(authority,amount)
    def start_url(self, authority:str)->str:
        return ZarinpalGateway().start_url(authority)

payment = PaymentService()
