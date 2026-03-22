from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_name: str = "Image to Vector API"
    jobs_dir: str = "../public/Assets"
    batch_run_id: str = ""
    max_upload_mb: int = 20
    max_dimension: int = 1536
    siliconflow_api_key: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    siliconflow_model: str = "stabilityai/stable-diffusion-xl-base-1.0"
    enable_tuned_prompts: bool = False
    enable_tuned_cleanup: bool = False
    enable_auto_selection: bool = False
    prompt_registry_version: str = "2026-03-22-r1"
    active_tuned_prompt_profile: str = "base_professional_pen"
    previous_tuned_prompt_profile: str = "legacy"
    allow_cors_origins: str = "*"


settings = Settings()
