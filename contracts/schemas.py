from pydantic import BaseModel, Field, ConfigDict

# これはサンプルです。実際のデータモデルに置き換えてください。
class ExampleModel(BaseModel):
    """
    AIエージェントへの指示:
    このモデルはSingle Source of Truthとして機能します。
    すべての入出力はこのディレクトリで定義されたPydanticモデルに準拠させてください。
    """
    id: int = Field(..., gt=0, description="ユニークID")
    name: str = Field(..., min_length=1, max_length=100, description="ユーザー名")
    is_active: bool = Field(default=True, description="有効フラグ")

    model_config = ConfigDict(extra="forbid") # 厳格なスキーマ検証を強制
