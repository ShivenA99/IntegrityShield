import uuid
from datetime import datetime

from sqlalchemy import MetaData, CheckConstraint, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import relationship

from . import db

# Use naming convention that works well with alembic autogenerate
metadata = MetaData(
    naming_convention={
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)


class StoredFile(db.Model):
    __tablename__ = "stored_files"
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    path = db.Column(db.Text, nullable=False, unique=True)
    mime_type = db.Column(db.Text, nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Backrefs defined on other models


class Assessment(db.Model):
    __tablename__ = "assessments"
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    attack_type = db.Column(db.Text, nullable=False)
    status = db.Column(db.Text, default="processed", nullable=False)

    # Foreign keys to files
    original_pdf_id = db.Column(UUID(as_uuid=True), db.ForeignKey("stored_files.id"))
    answers_pdf_id = db.Column(UUID(as_uuid=True), db.ForeignKey("stored_files.id"))
    attacked_pdf_id = db.Column(UUID(as_uuid=True), db.ForeignKey("stored_files.id"))
    report_pdf_id = db.Column(UUID(as_uuid=True), db.ForeignKey("stored_files.id"))

    # Relationships
    original_pdf = relationship("StoredFile", foreign_keys=[original_pdf_id])
    answers_pdf = relationship("StoredFile", foreign_keys=[answers_pdf_id])
    attacked_pdf = relationship("StoredFile", foreign_keys=[attacked_pdf_id])
    report_pdf = relationship("StoredFile", foreign_keys=[report_pdf_id])

    questions = relationship("Question", back_populates="assessment", cascade="all, delete-orphan")


class Question(db.Model):
    __tablename__ = "questions"
    id = db.Column(db.Integer, primary_key=True)
    assessment_id = db.Column(UUID(as_uuid=True), db.ForeignKey("assessments.id"), nullable=False)
    q_number = db.Column(db.Integer, nullable=False)

    stem_text = db.Column(db.Text, nullable=False)
    # Store options as JSON mapping option labels to text.
    options_json = db.Column(MutableDict.as_mutable(JSONB), nullable=False)
    gold_answer = db.Column(db.Text, nullable=False)
    gold_reason = db.Column(db.Text, nullable=True)
    wrong_answer = db.Column(db.Text, nullable=True)
    wrong_reason = db.Column(db.Text, nullable=True)
    attacked_stem = db.Column(db.Text, nullable=True)

    assessment = relationship("Assessment", back_populates="questions")
    llm_responses = relationship("LLMResponse", back_populates="question", cascade="all, delete-orphan")

    __table_args__ = (
        db.UniqueConstraint("assessment_id", "q_number", name="uq_questions_assessment_qnum"),
    )


class LLMResponse(db.Model):
    __tablename__ = "llm_responses"
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)
    model_name = db.Column(db.Text, nullable=False)
    llm_answer = db.Column(db.Text, nullable=False)
    llm_reason = db.Column(db.Text, nullable=True)
    raw_json = db.Column(JSONB, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    question = relationship("Question", back_populates="llm_responses")

    __table_args__ = (
        db.UniqueConstraint("question_id", "model_name", name="uq_llmresponses_question_model"),
    ) 