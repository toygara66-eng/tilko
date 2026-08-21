from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

WEAK_JWT_SECRETS = frozenset(
    {"", "tilko-dev-jwt-change-me", "change-me", "secret", "jwt-secret"}
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    hf_api_key: str = ""
    hf_model: str = "openai/gpt-oss-120b"
    hf_base_url: str = "https://router.huggingface.co/v1"
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-oss-120b"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "gemma2:9b"
    ollama_num_ctx: int = 8192
    llm_provider: str = "gemini"
    llm_fallback: str = "ollama"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    capture_training_data: bool = False
    elevenlabs_api_key: str = ""
    jwt_secret: str = "tilko-dev-jwt-change-me"
    jwt_expire_hours: int = 168
    app_env: str = "development"
    play_package_name: str = "com.tilko.app"
    play_billing_sandbox: bool = True
    play_webhook_secret: str = ""
    play_service_account_file: str = ""
    admin_api_secret: str = "tilko-admin-dev"
    cors_origins: str = "*"

    @property
    def is_local(self) -> bool:
        return self.llm_provider == "ollama"

    @property
    def active_model(self) -> str:
        if self.llm_provider == "ollama":
            return self.ollama_model
        if self.llm_provider == "gemini":
            return self.gemini_model
        if self.llm_provider == "huggingface":
            return self.hf_model
        if self.llm_provider == "groq":
            return self.groq_model
        if self.llm_provider == "openrouter":
            return self.openrouter_model
        return self.openai_model

    @property
    def is_tight_free_tier(self) -> bool:
        """Ücretsiz katmanlarda istek boyutu ve paralellik kısılır."""
        if self.llm_provider == "groq":
            return True
        if self.llm_provider == "openrouter":
            return self.openrouter_model.endswith(":free")
        return False

    @property
    def is_reasoning_model(self) -> bool:
        """Düşünme jetonu üreten modeller varsayılan çabayla dakikalarca bekletir."""
        model = (self.active_model or "").lower()
        return any(
            tag in model
            for tag in ("gpt-oss", "o1-", "o3-", "o4-", "deepseek-r1", "qwq")
        )

    @property
    def analyze_prompt_chars(self) -> int:
        """Hızlı analiz modeli uzun bağlamı kaldırır; tüm videoyu sığdırmaya çalışır."""
        if self.is_local:
            return 6000
        return 32000

    @property
    def questions_per_call(self) -> int:
        if self.is_local:
            return 5
        if self.is_tight_free_tier or self.is_reasoning_model:
            return 10
        return 25

    @property
    def max_parallel_calls(self) -> int:
        """Yerel model ve dar ücretsiz tavan paralel isteği cezalandırır."""
        if self.is_local or self.is_tight_free_tier:
            return 1
        return 2

    @property
    def max_analyze_chunks(self) -> int:
        """Video analizinde not turu sayısı; her parça ayrı LLM çağrısıdır."""
        if self.is_local or self.is_tight_free_tier or self.is_reasoning_model:
            return 1
        return 4

    @property
    def is_production(self) -> bool:
        return (self.app_env or "").strip().lower() in {"prod", "production"}

    @property
    def cors_origin_list(self) -> list[str]:
        raw = (self.cors_origins or "*").strip()
        if not raw or raw == "*":
            return ["*"]
        return [part.strip() for part in raw.split(",") if part.strip()]

    @model_validator(mode="after")
    def require_jwt_secret(self):
        secret = (self.jwt_secret or "").strip()
        admin = (self.admin_api_secret or "").strip()
        if self.is_production:
            if secret in WEAK_JWT_SECRETS or len(secret) < 32:
                raise ValueError(
                    "Üretimde JWT_SECRET ortam değişkeni zorunlu: en az 32 karakter "
                    "ve varsayılan 'tilko-dev-jwt-change-me' olamaz."
                )
            if admin in {"", "tilko-admin-dev", "change-me", "secret"} or len(admin) < 24:
                raise ValueError(
                    "Üretimde ADMIN_API_SECRET zorunlu: en az 24 karakter, varsayılan yasak."
                )
            if self.play_billing_sandbox:
                raise ValueError(
                    "Üretimde PLAY_BILLING_SANDBOX kapalı olmalı (false)."
                )
        elif not secret:
            self.jwt_secret = "tilko-dev-jwt-change-me"
        return self


settings = Settings()
