from typing import Dict, List
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi import File, UploadFile
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from config import *
import os
import base64

app = FastAPI()

'''app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)'''

DATABASE = f"postgresql://{user}:{password}@localhost:5432/{db_name}"
engine = create_engine(DATABASE)

Base = declarative_base()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Model(Base):
    __tablename__ = "models"

    id = Column(Integer, primary_key=True, index=True)
    name_model = Column(String, unique=True, nullable=False)
    files = relationship("ModelFile", back_populates="model")

class ModelFile(Base):
    __tablename__ = "model_files"

    id = Column(Integer, primary_key=True, index=True)
    model_id = Column(Integer, ForeignKey("models.id"), nullable=False)
    path = Column(String, nullable=False)
    description = Column(String, default=" ")
    name = Column(String, nullable=False)

    model = relationship("Model", back_populates="files")

class AddModelRequest(BaseModel):
    name_model: str

class AddFileRequest(BaseModel):
    name_model: str
    name: str
    description: str = ""
    file_content: str  # Base64-encoded

class GetModelFilesRequest(BaseModel):
    name_model: str

class DeleteFileRequest(BaseModel):
    name_model: str
    file_name: str

class DeleteAllFilesRequest(BaseModel):
    name_model: str

class ModelFileResponse(BaseModel):
    id: int
    path: str
    description: str
    model_id: int

# Добавление модели в бд (models)
@app.post("/add_model/")
async def add_model(request: AddModelRequest) -> Dict[str, str]:
    db = SessionLocal()
    try:
        existing_model = db.query(Model).filter(Model.name_model == request.name_model).first()
        if existing_model:
            raise HTTPException(status_code=400, detail="Повторное создание модели с одинаковым именем")
        new_model = Model(name_model=request.name_model)
        db.add(new_model)
        db.commit()
        db.refresh(new_model)

        return {"message": "Ok"}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        db.close()

# Добавление кастома к моделе (model_files)
@app.post("/add_file/")
async def add_file(request: AddFileRequest) -> Dict[str, str]:
    db = SessionLocal()
    try:
        existing_model = db.query(Model).filter(Model.name_model == request.name_model).first()
        if not existing_model:
            raise HTTPException(status_code=404, detail="Такой модели нету")

        upload_dir = uploads
        os.makedirs(upload_dir, exist_ok=True)
        file_name = request.name
        file_path = os.path.join(upload_dir, file_name)

        with open(file_path, "wb") as buffer:
            buffer.write(base64.b64decode(request.file_content))

        new_file = ModelFile(model_id=existing_model.id, path=file_path, description=request.description, name=request.name)
        db.add(new_file)
        db.commit()
        db.refresh(new_file)

        return {"message": "Ok"}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка: {e}")

    finally:
        db.close()

# Добавление кастома к модели 2 вариант (тут по параметрам, чтобы не делать encod на стороне клиента, мне кажется этот вариант лучше)
@app.post("/add_file2/")
async def add_file(
    name_model: str,
    name: str,
    description: str = "",
    file: UploadFile = File(...)
) -> Dict[str, str]:
    db = SessionLocal()
    try:
        existing_model = db.query(Model).filter(Model.name_model == name_model).first()
        if not existing_model:
            raise HTTPException(status_code=404, detail="Такой модели нету")

        upload_dir = uploads
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, name)

        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())

        new_file = ModelFile(model_id=existing_model.id, path=file_path, description=description, name=name)
        db.add(new_file)
        db.commit()
        db.refresh(new_file)

        return {"message": "Ok"}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка: {e}")

    finally:
        db.close()

# Получение всех кастомов конкретной модели (model_files)
@app.post("/get_model_files/")
async def get_model_files(request: GetModelFilesRequest) -> List[ModelFileResponse]:
    db = SessionLocal()
    try:
        existing_model = db.query(Model).filter(Model.name_model == request.name_model).first()
        if not existing_model:
            raise HTTPException(status_code=404, detail="Модели не существует")

        files = db.query(ModelFile).filter(ModelFile.model_id == existing_model.id).all()

        if not files:
            return {"message": "У этой модели нет кастомов", "files": []}

        return files

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка: {e}")

    finally:
        db.close()

# Удаление конкретного кастома из модели (model_files) +
@app.post("/delete_file/")
async def delete_file(request: DeleteFileRequest) -> Dict[str, str]:
    db = SessionLocal()
    try:
        existing_model = db.query(Model).filter(Model.name_model == request.name_model).first()
        if not existing_model:
            raise HTTPException(status_code=404, detail="Модели не существует")

        file_to_delete = db.query(ModelFile).filter(
            ModelFile.model_id == existing_model.id,
            ModelFile.name == request.file_name  # Используем имя файла для поиска
        ).first()

        if not file_to_delete:
            raise HTTPException(status_code=404, detail="Файл не найден")

        file_path = file_to_delete.path
        if os.path.exists(file_path):
            os.remove(file_path)

        db.delete(file_to_delete)
        db.commit()

        return {"message": "Файл успешно удален"}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка: {e}")

    finally:
        db.close()

# Удаление всех кастомов из конкретной модели (model_files)
@app.post("/delete_all_files_for_model/")
async def delete_all_files_for_model(request: DeleteAllFilesRequest) -> Dict[str, str]:
    db = SessionLocal()
    try:
        existing_model = db.query(Model).filter(Model.name_model == request.name_model).first()
        if not existing_model:
            raise HTTPException(status_code=404, detail="Модели не существует")

        files = db.query(ModelFile).filter(ModelFile.model_id == existing_model.id).all()
        if not files:
            return {"message": "У этой модели нет файлов для удаления"}

        for file in files:
            file_path = file.path
            if os.path.exists(file_path):
                os.remove(file_path)
            db.delete(file)

        db.commit()

        return {"message": "Все файлы модели успешно удалены"}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Ошибка: {e}")

    finally:
        db.close()
