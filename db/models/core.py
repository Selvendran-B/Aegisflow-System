from datetime import datetime
from uuid import UUID
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy import (
    DateTime, 
    Enum, 
    SmallInteger,
    String,
    Index,
    BigInteger,
    CHAR,
    Numeric,
    text,
    ForeignKey,
)
from sqlalchemy.orm import Mapped, mapped_column

from db.base import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    holder_name: Mapped[str] = mapped_column(String, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    risk_tier: Mapped[str] = mapped_column(
        Enum("low", "medium", "high", name="risk_tier"),
        nullable=False,
    )
    kyc_level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    __table_args__ = (
        Index("ix_accounts_risk_tier","risk_tier"),
    )

class Device(Base):
    __tablename__ = "devices"

    id:Mapped[UUID] = mapped_column(primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String,nullable=False)
    first_seen: Mapped[datetime]= mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    reputation: Mapped[float]=mapped_column(nullable=False)

class IP(Base):
    __tablename__ = "ips"

    id:Mapped[UUID] = mapped_column(primary_key=True)
    ip:Mapped[str] =  mapped_column(INET,nullable=False)
    firstseen: Mapped[datetime]=mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    reputation:Mapped[float]= mapped_column(nullable=False)

class Merchant(Base):
    __tablename__="merchants"

    id:Mapped[UUID]= mapped_column(primary_key=True)
    mcc: Mapped[str]= mapped_column(String,nullable=False)
    firstseen: Mapped[datetime]=mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    reputation:Mapped[float]= mapped_column(nullable=False)

class EntityEdge(Base):
    __tablename__="entity_edges"

    id:Mapped[int] = mapped_column(BigInteger,primary_key=True,autoincrement=True)

    src_type:Mapped[str] = mapped_column(String,nullable = False)
    src_id:Mapped[UUID]=mapped_column(nullable=False)

    dst_type:Mapped[str]=mapped_column(String,nullable=False)
    dst_id:Mapped[UUID]=mapped_column(nullable=False)

    edge_type:Mapped[str]=mapped_column(String(32),nullable = False)

    first_seen:Mapped[datetime]=mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    weight:Mapped[float]=mapped_column(nullable=False)
    __table_args__ = (
        Index(
            "ix_entity_edges_src",
            "src_type",
            "src_id",
        ),
        Index(
            "ix_entity_edges_dst",
            "dst_type",
            "dst_id",
        ),
    )

class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[UUID] = mapped_column(primary_key=True)

    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    account_id: Mapped[UUID] = mapped_column(
        ForeignKey("accounts.id"),
        nullable=False,
    )

    counterparty_id: Mapped[UUID] = mapped_column(
        nullable=False,
    )

    merchant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("merchants.id"),
        nullable=True,
    )

    device_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("devices.id"),
        nullable=True,
    )

    ip_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("ips.id"),
        nullable=True,
    )

    amount: Mapped[float] = mapped_column(
        Numeric(14, 2),
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        CHAR(3),
        nullable=False,
    )

    channel: Mapped[str] = mapped_column(
        Enum("card", "transfer", "wallet", name="transaction_channel"),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    __table_args__ = (
        Index(
            "ix_transactions_account_ts",
            "account_id",
            text("ts DESC"),
        ),
        Index(
            "ix_transactions_ts_brin",
            "ts",
            postgresql_using="brin",
        ),
    )

class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[UUID] = mapped_column(primary_key=True)

    transaction_id: Mapped[UUID] = mapped_column(
        ForeignKey("transactions.id"),
        nullable=False,
        unique=True,
    )

    score: Mapped[float] = mapped_column(nullable=False)

    calibrated_prob: Mapped[float] = mapped_column(nullable=False)

    decision: Mapped[str] = mapped_column(
        Enum(
            "approve",
            "review",
            "decline",
            name="decision_type",
        ),
        nullable=False,
    )

    reason_codes: Mapped[dict] = mapped_column(JSONB,nullable=False)

    rule_hits: Mapped[dict] = mapped_column(JSONB,nullable=False)

    model_version: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    latency_ms: Mapped[float] = mapped_column(nullable=False)

    degraded: Mapped[bool] = mapped_column(nullable=False)

    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "ix_decisions_decision_ts",
            "decision",
            text("ts DESC"),
        ),
    )

class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[UUID] = mapped_column(primary_key=True)

    transaction_id: Mapped[UUID] = mapped_column(
        ForeignKey("transactions.id"),
        nullable=False,
    )

    alert_type: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    severity: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    case_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("cases.id"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

class Case(Base):
    __tablename__ = "cases"

    id: Mapped[UUID] = mapped_column(primary_key=True)

    title: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    priority: Mapped[float] = mapped_column(
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        Enum(
            "open",
            "investigating",
            "pending_review",
            "closed",
            name="case_status",
        ),
        nullable=False,
    )

    assigned_to: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    sla_due: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    disposition: Mapped[str | None] = mapped_column(
        Enum(
            "fraud",
            "not_fraud",
            "sar_filed",
            name="case_disposition",
        ),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

class EvidenceItem(Base):
    __tablename__ = "evidence_items"

    id: Mapped[UUID] = mapped_column(primary_key=True)

    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id"),
        nullable=False,
    )

    kind: Mapped[str] = mapped_column(
        Enum(
            "graph",
            "timeline",
            "typology",
            "media",
            "note",
            name="evidence_kind",
        ),
        nullable=False,
    )

    payload: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )

    source_ref: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )

    created_by: Mapped[str] = mapped_column(
        Enum(
            "agent",
            "human",
            name="evidence_creator",
        ),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

class SARDraft(Base):
    __tablename__ = "sar_drafts"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
    )

    case_id: Mapped[UUID] = mapped_column(
        ForeignKey("cases.id"),
        nullable=False,
    )

    version: Mapped[int] = mapped_column(
        nullable=False,
    )

    narrative_md: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    citations: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        Enum(
            "draft",
            "edited",
            "approved",
            "rejected",
            name="sar_status",
        ),
        nullable=False,
    )

    author: Mapped[str] = mapped_column(
        Enum(
            "agent",
            "analyst",
            name="sar_author",
        ),
        nullable=False,
    )

    reviewed_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "uq_sar_case_version",
            "case_id",
            "version",
            unique=True,
        ),
    )

class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
    )

    username: Mapped[str] = mapped_column(
        String,
        nullable=False,
        unique=True,
    )

    role: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    action: Mapped[str] = mapped_column(

        String,
        nullable=False,
    )

    entity_type: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    entity_id: Mapped[UUID | None] = mapped_column(
        nullable=True,
    )

    details: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

class GroundTruthLabel(Base):
    __tablename__ = "ground_truth_labels"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
    )

    transaction_id: Mapped[UUID] = mapped_column(
        ForeignKey("transactions.id"),
        nullable=False,
    )

    label: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    typology: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

class SanctionsList(Base):
    __tablename__ = "sanctions_list"

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
    )

    entity_name: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    entity_type: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    source: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    external_id: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )