from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any

# 契約（Contract）定義
# このファイルがこのサイクルの「正解」となります。
# 変更する場合は必ずこのファイルを更新し、再整合させてください。

class CycleInput(BaseModel):
    """入力データの仕様"""
    model_config = ConfigDict(extra='forbid') # 厳格モード: 定義されていないフィールドは禁止

    request_id: str = Field(..., description="リクエストID")
    payload: Dict[str, Any] = Field(default_factory=dict, description="処理対象データ")

class CycleOutput(BaseModel):
    """出力データの仕様"""
    success: bool = Field(..., description="処理成功フラグ")
    data: Optional[Dict[str, Any]] = Field(None, description="結果データ")
    error_message: Optional[str] = Field(None, description="エラー時のメッセージ")
