"""
app/db/models.py
────────────────
SQLAlchemy 2.0-style ORM models for EklavyaX.

All models use Mapped[] + mapped_column() for full type-safety.
Relationships use back_populates for bidirectional navigation.
"""
from __future__ import annotations

import enum
from datetime import date, datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    student = "student"
    teacher = "teacher"
    admin = "admin"


class ChallengeStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    completed = "completed"
    cancelled = "cancelled"


# ─────────────────────────────────────────────────────────────────────────────
# Faction
# ─────────────────────────────────────────────────────────────────────────────

class Faction(Base):
    """
    One of four permanent houses a user is sorted into on registration.
    Faction score aggregates XP from all its members.
    """
    __tablename__ = "factions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    color_hex: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)  # e.g. "#FF6B35"
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    icon_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Relationships
    users: Mapped[List["User"]] = relationship("User", back_populates="faction")

    def __repr__(self) -> str:
        return f"<Faction id={self.id} name={self.name!r} score={self.score}>"


# ─────────────────────────────────────────────────────────────────────────────
# User
# ─────────────────────────────────────────────────────────────────────────────

class User(Base):
    """Core user model. Handles all three roles: student, teacher, admin."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="userrole"), default=UserRole.student, nullable=False
    )
    avatar_url: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    roll: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    grade: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    school: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    target_exam: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    faction_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("factions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    faction: Mapped[Optional["Faction"]] = relationship("Faction", back_populates="users")
    streak: Mapped[Optional["Streak"]] = relationship(
        "Streak", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    wallet: Mapped[Optional["Wallet"]] = relationship(
        "Wallet", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction", back_populates="user", cascade="all, delete-orphan"
    )
    bounties_created: Mapped[List["Bounty"]] = relationship(
        "Bounty", back_populates="teacher", cascade="all, delete-orphan"
    )
    bounty_submissions: Mapped[List["BountySubmission"]] = relationship(
        "BountySubmission",
        back_populates="student",
        foreign_keys="BountySubmission.student_id",
        cascade="all, delete-orphan",
    )
    ai_logs: Mapped[List["AIExplanationLog"]] = relationship(
        "AIExplanationLog", back_populates="user", cascade="all, delete-orphan"
    )
    challenges_as_challenger: Mapped[List["Challenge"]] = relationship(
        "Challenge",
        back_populates="challenger",
        foreign_keys="Challenge.challenger_id",
    )
    challenges_as_opponent: Mapped[List["Challenge"]] = relationship(
        "Challenge",
        back_populates="opponent",
        foreign_keys="Challenge.opponent_id",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r} role={self.role}>"


# ─────────────────────────────────────────────────────────────────────────────
# Streak
# ─────────────────────────────────────────────────────────────────────────────

class Streak(Base):
    """
    Daily learning streak tracker.
    Maintains current streak, longest streak, and freeze token count.
    """
    __tablename__ = "streaks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    current_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    longest_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_activity_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    streak_freezes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="streak")

    def __repr__(self) -> str:
        return (
            f"<Streak user_id={self.user_id} "
            f"current={self.current_streak} longest={self.longest_streak}>"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Wallet
# ─────────────────────────────────────────────────────────────────────────────

class Wallet(Base):
    """
    Virtual economy wallet.
    balance = EduCoins (spendable currency)
    xp      = Experience Points (non-spendable, drives leaderboard)
    """
    __tablename__ = "wallets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="wallet")

    def __repr__(self) -> str:
        return f"<Wallet user_id={self.user_id} balance={self.balance} xp={self.xp}>"


# ─────────────────────────────────────────────────────────────────────────────
# Transaction
# ─────────────────────────────────────────────────────────────────────────────

class Transaction(Base):
    """
    Immutable ledger of all coin movements.
    amount > 0 = credit, amount < 0 = debit.
    """
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    xp_change: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reason: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="transactions")

    def __repr__(self) -> str:
        return f"<Transaction id={self.id} user_id={self.user_id} amount={self.amount} reason={self.reason!r}>"


# ─────────────────────────────────────────────────────────────────────────────
# Bounty
# ─────────────────────────────────────────────────────────────────────────────

class Bounty(Base):
    """
    Teacher-posted time-limited challenge on a specific topic.
    Students earn reward_coins upon teacher approval.
    """
    __tablename__ = "bounties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    teacher_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    topic: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    reward_coins: Mapped[int] = mapped_column(Integer, nullable=False)
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    teacher: Mapped["User"] = relationship("User", back_populates="bounties_created")
    submissions: Mapped[List["BountySubmission"]] = relationship(
        "BountySubmission", back_populates="bounty", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Bounty id={self.id} title={self.title!r} active={self.is_active}>"


# ─────────────────────────────────────────────────────────────────────────────
# BountySubmission
# ─────────────────────────────────────────────────────────────────────────────

class BountySubmission(Base):
    """Student's claim that they completed a bounty. Requires teacher approval."""

    __tablename__ = "bounty_submissions"
    __table_args__ = (
        UniqueConstraint("bounty_id", "student_id", name="uq_bounty_student"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    bounty_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bounties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    is_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)   # 0-100 percentage

    # Relationships
    bounty: Mapped["Bounty"] = relationship("Bounty", back_populates="submissions")
    student: Mapped["User"] = relationship(
        "User",
        back_populates="bounty_submissions",
        foreign_keys=[student_id],
    )

    def __repr__(self) -> str:
        return (
            f"<BountySubmission id={self.id} "
            f"bounty_id={self.bounty_id} student_id={self.student_id} "
            f"approved={self.is_approved}>"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Challenge
# ─────────────────────────────────────────────────────────────────────────────

class Challenge(Base):
    """
    1v1 peer challenge with optional EduCoin wager.
    Supports both targeted (opponent_id set) and open challenges.
    """
    __tablename__ = "challenges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    challenger_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    opponent_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    topic: Mapped[str] = mapped_column(String(100), nullable=False)
    wager_coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[ChallengeStatus] = mapped_column(
        Enum(ChallengeStatus, name="challengestatus"),
        default=ChallengeStatus.pending,
        nullable=False,
    )
    winner_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    challenger: Mapped["User"] = relationship(
        "User",
        back_populates="challenges_as_challenger",
        foreign_keys=[challenger_id],
    )
    opponent: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="challenges_as_opponent",
        foreign_keys=[opponent_id],
    )
    winner: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[winner_id],
    )
    results: Mapped[List["ChallengeResult"]] = relationship(
        "ChallengeResult", back_populates="challenge", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<Challenge id={self.id} "
            f"challenger={self.challenger_id} vs opponent={self.opponent_id} "
            f"status={self.status}>"
        )


# ─────────────────────────────────────────────────────────────────────────────
# ChallengeResult
# ─────────────────────────────────────────────────────────────────────────────

class ChallengeResult(Base):
    """Per-question performance record for a challenge."""

    __tablename__ = "challenge_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    challenge_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("challenges.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[str] = mapped_column(String(100), nullable=False)
    student_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    time_taken_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Relationships
    challenge: Mapped["Challenge"] = relationship("Challenge", back_populates="results")
    student: Mapped["User"] = relationship("User", foreign_keys=[student_id])

    def __repr__(self) -> str:
        return (
            f"<ChallengeResult id={self.id} "
            f"challenge={self.challenge_id} student={self.student_id} correct={self.correct}>"
        )


# ─────────────────────────────────────────────────────────────────────────────
# AIExplanationLog
# ─────────────────────────────────────────────────────────────────────────────

class AIExplanationLog(Base):
    """
    Immutable log of every Synapse.ai explain call.
    Used to track coin expenditure and power the "Good Student" refund mechanic.
    """
    __tablename__ = "ai_explanation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    highlighted_text: Mapped[str] = mapped_column(Text, nullable=False)
    target_language: Mapped[str] = mapped_column(String(50), default="Simple English", nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    cost_coins: Mapped[int] = mapped_column(Integer, nullable=False)
    refunded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="ai_logs")

    def __repr__(self) -> str:
        return (
            f"<AIExplanationLog id={self.id} "
            f"user_id={self.user_id} cost={self.cost_coins} refunded={self.refunded}>"
        )


# ─────────────────────────────────────────────────────────────────────────────
# RewardAuditLog
# ─────────────────────────────────────────────────────────────────────────────

class ReasonCode(str, enum.Enum):
    granted = "granted"
    cooldown_violation = "cooldown_violation"
    cap_exceeded = "cap_exceeded"
    pattern_flagged = "pattern_flagged"
    invalid_answer = "invalid_answer"


class RewardAuditLog(Base):
    """
    Queryable audit log for every reward grant, rejection, or flag.
    Every call through the safeguarded reward pipeline writes here.
    """
    __tablename__ = "reward_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    reward_coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reward_xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reason_code: Mapped[ReasonCode] = mapped_column(
        Enum(ReasonCode, name="reasoncode"), nullable=False
    )
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationship
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])

    def __repr__(self) -> str:
        return (
            f"<RewardAuditLog id={self.id} user={self.user_id} "
            f"reason={self.reason_code} coins={self.reward_coins} xp={self.reward_xp}>"
        )


# ─────────────────────────────────────────────────────────────────────────────
# QuizQuestion
# ─────────────────────────────────────────────────────────────────────────────

class QuizQuestion(Base):
    """
    Server-side question bank entry.
    correct_option_index is the 0-based index into the canonical options list.
    """
    __tablename__ = "quiz_questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    topic: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    option_a: Mapped[str] = mapped_column(String(500), nullable=False)
    option_b: Mapped[str] = mapped_column(String(500), nullable=False)
    option_c: Mapped[str] = mapped_column(String(500), nullable=False)
    option_d: Mapped[str] = mapped_column(String(500), nullable=False)
    correct_option_index: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-3
    difficulty: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    preview_coins: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    preview_xp: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def get_canonical_options(self) -> list[str]:
        return [self.option_a, self.option_b, self.option_c, self.option_d]

    def __repr__(self) -> str:
        return f"<QuizQuestion id={self.id} topic={self.topic!r}>"


# ─────────────────────────────────────────────────────────────────────────────
# QuizSession
# ─────────────────────────────────────────────────────────────────────────────

class QuizSession(Base):
    """
    Tracks a single question attempt within a quiz.
    question_shown_at is SERVER-recorded; never trust the client.
    shuffled_order stores the permutation (e.g. "2,0,3,1") so we can
    map the client's chosen index back to the canonical correct index.
    """
    __tablename__ = "quiz_sessions"
    __table_args__ = (
        UniqueConstraint("quiz_run_id", "question_id", name="uq_run_question"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    quiz_run_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("quiz_questions.id", ondelete="CASCADE"), nullable=False
    )
    question_index: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-based position
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    shuffled_order: Mapped[str] = mapped_column(String(20), nullable=False)  # e.g. "2,0,3,1"
    question_shown_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    selected_option_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_correct: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    coins_awarded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    xp_awarded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejection_reason: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])
    question: Mapped["QuizQuestion"] = relationship("QuizQuestion", foreign_keys=[question_id])

    def __repr__(self) -> str:
        return (
            f"<QuizSession id={self.id} run={self.quiz_run_id} "
            f"user={self.user_id} q={self.question_id}>"
        )


# ─────────────────────────────────────────────────────────────────────────────
# UserResponseMetric
# ─────────────────────────────────────────────────────────────────────────────

class UserResponseMetric(Base):
    """
    Rolling record of response times and accuracy per user.
    Used by the pattern-detection engine to compute z-scores.
    """
    __tablename__ = "user_response_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[int] = mapped_column(Integer, nullable=False)
    response_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<UserResponseMetric user={self.user_id} "
            f"time={self.response_time_ms}ms correct={self.is_correct}>"
        )


# ─────────────────────────────────────────────────────────────────────────────
# FactionBattle
# ─────────────────────────────────────────────────────────────────────────────

class BattleStatus(str, enum.Enum):
    scheduled = "scheduled"
    active = "active"
    completed = "completed"


class FactionBattle(Base):
    """
    A time-windowed Faction Wars battle event.
    All factions compete during the window; scores aggregate from validated rewards.
    """
    __tablename__ = "faction_battles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(200), default="Faction Wars", nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[BattleStatus] = mapped_column(
        Enum(BattleStatus, name="battlestatus"),
        default=BattleStatus.scheduled,
        nullable=False,
    )
    winning_faction_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("factions.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    scores: Mapped[List["FactionBattleScore"]] = relationship(
        "FactionBattleScore", back_populates="battle", cascade="all, delete-orphan"
    )
    contributions: Mapped[List["FactionBattleContribution"]] = relationship(
        "FactionBattleContribution", back_populates="battle", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<FactionBattle id={self.id} status={self.status} title={self.title!r}>"


# ─────────────────────────────────────────────────────────────────────────────
# FactionBattleScore
# ─────────────────────────────────────────────────────────────────────────────

class FactionBattleScore(Base):
    """
    Aggregated score per faction per battle.
    Only incremented from validated (post-safeguard) rewards.
    """
    __tablename__ = "faction_battle_scores"
    __table_args__ = (
        UniqueConstraint("battle_id", "faction_id", name="uq_battle_faction"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    battle_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("faction_battles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    faction_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("factions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    total_xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    contributor_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    battle: Mapped["FactionBattle"] = relationship("FactionBattle", back_populates="scores")
    faction: Mapped["Faction"] = relationship("Faction", foreign_keys=[faction_id])

    def __repr__(self) -> str:
        return (
            f"<FactionBattleScore battle={self.battle_id} "
            f"faction={self.faction_id} xp={self.total_xp}>"
        )


# ─────────────────────────────────────────────────────────────────────────────
# FactionBattleContribution
# ─────────────────────────────────────────────────────────────────────────────

class FactionBattleContribution(Base):
    """
    Individual user contribution to a faction battle.
    Tracks XP contributed through validated quiz rewards.
    """
    __tablename__ = "faction_battle_contributions"
    __table_args__ = (
        UniqueConstraint("battle_id", "user_id", name="uq_battle_user"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    battle_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("faction_battles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    faction_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("factions.id", ondelete="CASCADE"), nullable=False
    )
    xp_contributed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    questions_answered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    battle: Mapped["FactionBattle"] = relationship("FactionBattle", back_populates="contributions")
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])

    def __repr__(self) -> str:
        return (
            f"<FactionBattleContribution battle={self.battle_id} "
            f"user={self.user_id} xp={self.xp_contributed}>"
        )
