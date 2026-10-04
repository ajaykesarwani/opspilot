from typing import Annotated

from fastapi import Depends, Request

from opspilot_persistence.repositories.base import RequestRepository
from opspilot_api.settings import Settings
from opspilot_messaging import EventPublisher
from opspilot_rag import VectorStore


def get_repository(request: Request) -> RequestRepository:
    return request.app.state.request_repository

def get_publisher(request: Request) -> EventPublisher:
    return request.app.state.publisher

def get_vector_store(request: Request) -> VectorStore:
    return request.app.state.vector_store

def get_settings(request: Request) -> Settings:
    return request.app.state.settings


RepositoryDep = Annotated[RequestRepository, Depends(get_repository)]
PublisherDep = Annotated[EventPublisher, Depends(get_publisher)]
VectorStoreDep = Annotated[VectorStore, Depends(get_vector_store)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

