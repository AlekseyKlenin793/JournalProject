from sqlalchemy import Column, Integer, String, Text, Numeric, Date, ForeignKey, TIMESTAMP
from sqlalchemy.orm import relationship
from db import Base


class Journal(Base):
    __tablename__ = "journals"
    id = Column(Integer, primary_key=True)
    journal_name = Column(String(1000), nullable=False)
    issn = Column(String(20), nullable=False)
    inclusion_date = Column(Date)
    h_index = Column(Numeric)
    citation_index = Column(Numeric)
    publication_time_value = Column(Numeric)
    publication_time_unit = Column(String(20))
    publication_price = Column(Numeric)
    publication_currency = Column(String(10))
    url = Column(Text)
    final_category = Column(String(100))
    timestamp = Column(TIMESTAMP)
    white_list_level_2023 = Column(String(100))
    white_list_level_2025 = Column(String(100))
    directions = relationship("Direction", back_populates="journal")


class Direction(Base):
    __tablename__ = "directions"
    id = Column(Integer, primary_key=True)
    journal_id = Column(Integer, ForeignKey("journals.id"))
    direction_number = Column(String(100))
    scientific_direction = Column(Text)
    journal = relationship("Journal", back_populates="directions")
