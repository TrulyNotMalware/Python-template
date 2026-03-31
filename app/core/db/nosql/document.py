from pydantic import BaseModel, ConfigDict


class MongoDocument(BaseModel):
    id: str | None = None

    model_config = ConfigDict(populate_by_name=True)
