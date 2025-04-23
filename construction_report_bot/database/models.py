from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text, Boolean, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

# Связующая таблица для связи многие-ко-многим между объектами и заказчиками
client_objects = Table(
    'client_objects', 
    Base.metadata,
    Column('client_id', Integer, ForeignKey('clients.id')),
    Column('object_id', Integer, ForeignKey('objects.id'))
)

# Связующая таблица для связи многие-ко-многим между отчетами и ИТР
report_itr = Table(
    'report_itr', 
    Base.metadata,
    Column('report_id', Integer, ForeignKey('reports.id')),
    Column('itr_id', Integer, ForeignKey('itr.id'))
)

# Связующая таблица для связи многие-ко-многим между отчетами и рабочими
report_workers = Table(
    'report_workers', 
    Base.metadata,
    Column('report_id', Integer, ForeignKey('reports.id')),
    Column('worker_id', Integer, ForeignKey('workers.id'))
)

# Связующая таблица для связи многие-ко-многим между отчетами и техникой
report_equipment = Table(
    'report_equipment', 
    Base.metadata,
    Column('report_id', Integer, ForeignKey('reports.id')),
    Column('equipment_id', Integer, ForeignKey('equipment.id')),
    Column('quantity', Integer, default=1)
)

class User(Base):
    """Модель для всех пользователей системы"""
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=True)
    username = Column(String(100), nullable=True)
    role = Column(String(50), nullable=False)  # admin, client
    access_code = Column(String(100), nullable=True)  # Код для первого входа
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Отношения
    client = relationship("Client", back_populates="user", uselist=False)

class Client(Base):
    """Модель для заказчиков"""
    __tablename__ = 'clients'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), unique=True)
    full_name = Column(String(255), nullable=False)
    organization = Column(String(255), nullable=False)
    contact_info = Column(String(255), nullable=True)
    
    # Отношения
    user = relationship("User", back_populates="client")
    objects = relationship("Object", secondary=client_objects, back_populates="clients")

class Object(Base):
    """Модель для строительных объектов"""
    __tablename__ = 'objects'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    
    # Отношения
    clients = relationship("Client", secondary=client_objects, back_populates="objects")
    reports = relationship("Report", back_populates="object")

class ITR(Base):
    """Модель для инженерно-технических работников"""
    __tablename__ = 'itr'
    
    id = Column(Integer, primary_key=True)
    full_name = Column(String(255), nullable=False)
    
    # Отношения
    reports = relationship("Report", secondary=report_itr, back_populates="itr_personnel")

class Worker(Base):
    """Модель для рабочих"""
    __tablename__ = 'workers'
    
    id = Column(Integer, primary_key=True)
    full_name = Column(String(255), nullable=False)
    position = Column(String(255), nullable=False)
    
    # Отношения
    reports = relationship("Report", secondary=report_workers, back_populates="workers")

class Equipment(Base):
    """Модель для строительной техники"""
    __tablename__ = 'equipment'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    
    # Отношения
    reports = relationship("Report", secondary=report_equipment, back_populates="equipment")

class Report(Base):
    """Модель для отчетов"""
    __tablename__ = 'reports'
    
    id = Column(Integer, primary_key=True)
    object_id = Column(Integer, ForeignKey('objects.id'), nullable=False)
    date = Column(DateTime, default=datetime.utcnow)
    type = Column(String(50), nullable=False)  # morning, evening
    report_type = Column(String(100), nullable=False)  # Тип работ (инженерные коммуникации и т.д.)
    work_subtype = Column(String(100), nullable=True)  # Подтип работ (отопление, вентиляция и т.д.)
    comments = Column(Text, nullable=True)
    status = Column(String(50), default="draft")  # draft, sent
    sent_at = Column(DateTime, nullable=True)
    recipient_id = Column(Integer, ForeignKey('users.id'), nullable=True)  # ID получателя отчета
    
    # Отношения
    object = relationship("Object", back_populates="reports")
    itr_personnel = relationship("ITR", secondary=report_itr, back_populates="reports")
    workers = relationship("Worker", secondary=report_workers, back_populates="reports")
    equipment = relationship("Equipment", secondary=report_equipment, back_populates="reports")
    photos = relationship("ReportPhoto", back_populates="report")
    recipient = relationship("User", foreign_keys=[recipient_id])

class ReportPhoto(Base):
    """Модель для фотографий в отчетах"""
    __tablename__ = 'report_photos'
    
    id = Column(Integer, primary_key=True)
    report_id = Column(Integer, ForeignKey('reports.id'), nullable=False)
    file_path = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    
    # Отношения
    report = relationship("Report", back_populates="photos") 