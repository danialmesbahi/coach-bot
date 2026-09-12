from functools import lru_cache
from urllib.parse import urlsplit
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str
    database_url: str
    redis_url: str
    sensi_id: int
    admin_team_ids: str = ''
    platform_team_ids: str = ''
    support_username: str = ''
    bot_username: str = 'isensir_bot'
    development_team_percent: int = Field(
        default=50,
        ge=0,
        le=100,
        validation_alias=AliasChoices('DEVELOPMENT_TEAM_PERCENT', 'ADMIN_COMMISSION_PERCENT'),
    )
    timezone: str = 'Asia/Tehran'
    log_level: str = 'INFO'
    app_env: str = 'development'
    payment_mode: str = 'both'
    zarinpal_merchant_id: str = ''
    zarinpal_callback_url: str = ''
    card_to_card_title: str = 'پرداخت کارت به کارت'
    card_to_card_bank_info: str = 'شماره کارت را در اینجا قرار دهید'
    public_base_url: str = ''
    webhook_secret: str = ''
    max_plan_file_mb: int = Field(default=10, ge=1, le=50)
    max_body_photo_mb: int = Field(default=10, ge=1, le=20)
    rate_limit_per_minute: int = Field(default=30, ge=5, le=300)
    db_pool_min: int = Field(default=3, ge=1, le=20)
    db_pool_max: int = Field(default=25, ge=5, le=80)
    bot_concurrency: int = Field(default=200, ge=20, le=1000)
    motivation_enabled: bool = True
    motivation_interval_days: int = Field(default=3, ge=1, le=30)
    motivation_batch_size: int = Field(default=20, ge=1, le=100)
    motivation_check_minutes: int = Field(default=60, ge=15, le=1440)
    migrate_on_start: bool = True
    web_dev_login: bool = False
    web_session_hours: int = Field(default=12, ge=1, le=72)
    # Enable only behind our isolated ingress, which overwrites X-Coach-Client-IP.
    web_trust_ingress: bool = False
    model_config = SettingsConfigDict(env_file=('.env', '.env.live'), env_file_encoding='utf-8', extra='ignore')

    @property
    def admin_team(self) -> set[int]:
        return {int(x.strip()) for x in self.admin_team_ids.split(',') if x.strip()}

    @property
    def platform_team(self) -> set[int]:
        ids = {int(x.strip()) for x in self.platform_team_ids.split(',') if x.strip()}
        if any(value <= 0 for value in ids):
            raise ValueError('Platform Telegram IDs must be positive')
        return ids

    def role(self, telegram_id: int) -> str:
        if telegram_id == self.sensi_id:
            return 'sensi'
        if telegram_id in self.admin_team:
            return 'admin_team'
        return 'customer'

    @property
    def support_url(self) -> str:
        username=self.support_username.strip().lstrip('@')
        if username:
            return f'https://t.me/{username}'
        return f'tg://user?id={self.sensi_id}'

    @property
    def resolved_zarinpal_callback(self):
        return self.zarinpal_callback_url or (self.public_base_url.rstrip('/') + '/payment/zarinpal/callback' if self.public_base_url else '')

    def validate_runtime(self):
        if self.sensi_id <= 0:
            raise RuntimeError('SENSI_ID must be a valid positive Telegram numeric ID')
        if not self.bot_token or ':' not in self.bot_token:
            raise RuntimeError('BOT_TOKEN is missing or malformed')
        if self.db_pool_min > self.db_pool_max:
            raise RuntimeError('DB_POOL_MIN cannot exceed DB_POOL_MAX')
        try:
            self.admin_team
            self.platform_team
        except ValueError as exc:
            raise RuntimeError('ADMIN_TEAM_IDS must contain only numeric Telegram IDs') from exc
        mode = self.payment_mode.lower()
        if mode not in {'mock', 'card_to_card', 'zarinpal', 'both'}:
            raise RuntimeError('PAYMENT_MODE must be mock, card_to_card, zarinpal, or both')
        if self.app_env.lower() == 'production':
            if self.web_dev_login:
                raise RuntimeError('WEB_DEV_LOGIN is forbidden in production')
            if mode == 'mock':
                raise RuntimeError('PAYMENT_MODE=mock is forbidden in production')
            if not self.webhook_secret or len(self.webhook_secret) < 32:
                raise RuntimeError('WEBHOOK_SECRET must be at least 32 characters in production')
            if not self.public_base_url.startswith('https://'):
                raise RuntimeError('PUBLIC_BASE_URL must use HTTPS in production')
            if mode in {'zarinpal', 'both'} and not self.zarinpal_merchant_id:
                raise RuntimeError('ZARINPAL_MERCHANT_ID is required when ZarinPal is enabled')
            if mode in {'zarinpal', 'both'}:
                callback = urlsplit(self.resolved_zarinpal_callback)
                if callback.scheme != 'https' or not callback.hostname or callback.username or callback.fragment:
                    raise RuntimeError('ZARINPAL_CALLBACK_URL must be a valid HTTPS callback URL')
            if mode in {'card_to_card', 'both'} and self.card_to_card_bank_info == 'شماره کارت را در اینجا قرار دهید':
                raise RuntimeError('CARD_TO_CARD_BANK_INFO must be configured for production')


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.validate_runtime()
    return s
