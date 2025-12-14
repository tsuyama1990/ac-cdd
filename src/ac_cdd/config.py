from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    MAX_RETRIES: int = 10

    # Audit Prompts
    AUDITOR_PROMPT: str = (
        "あなたは世界一厳格なコード監査人です。"
        "Pydantic契約違反、セキュリティ、設計原則の観点からコードをレビューしてください。"
        "合格なら `{\"approved\": true}`、"
        "不合格なら `{\"approved\": false, \"comments\": [...]}` をJSONで返してください。"
    )

    PROPERTY_TEST_PROMPT_TEMPLATE: str = (
        "実装は見ず、このPydanticスキーマ (contracts/) の制約が正しく機能するかを検証する "
        "Hypothesisテストを作成せよ。出力先は tests/property/test_cycle{cycle_id}.py"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
