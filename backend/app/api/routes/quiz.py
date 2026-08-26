from __future__ import annotations

import random
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import get_current_user, require_role
from app.db import models
from app.db.database import get_db
from app.services.ai_service import sanitize_latex_to_unicode
from app.schemas.quiz_sch import (
    QuizAnswerSummary,
    QuizNextResponse,
    QuizQuestionResponse,
    QuizStartRequest,
    QuizStartResponse,
    QuizSubmitRequest,
    QuizSubmitResponse,
    QuizSummaryResponse,
)
from app.services.safeguards import (
    generate_shuffled_options,
    grant_safeguarded_reward,
    permutation_to_str,
    str_to_permutation,
)

router = APIRouter(prefix="/quiz", tags=["Quiz"])



@router.post(
    "/generate-ai",
    summary="Generate new STEM questions on-the-fly using AI and add to question bank",
)
async def generate_ai_quiz(
    topic: str = "Physics",
    num_questions: int = 5,
    current_user: models.User = Depends(require_role("student", "teacher", "admin")),
    db: Session = Depends(get_db),
):
    
    from app.services.ai_service import generate_ai_quiz_questions

    generated = await generate_ai_quiz_questions(topic=topic, num_questions=num_questions)
    saved_questions = []

    for q_data in generated:
        q = models.QuizQuestion(**q_data)
        db.add(q)
        saved_questions.append(q)

    db.commit()
    return {
        "success": True,
        "message": f"Successfully generated {len(saved_questions)} new AI questions for topic '{topic}'.",
        "count": len(saved_questions),
    }



def _run_async(coro):
    import asyncio
    import concurrent.futures
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result(timeout=12)
    else:
        return asyncio.run(coro)


@router.post(
    "/start",
    response_model=QuizStartResponse,
    summary="Start a new quiz run with fresh dynamic questions from Groq AI",
)
def start_quiz(
    payload: QuizStartRequest,
    current_user: models.User = Depends(require_role("student", "admin")),
    db: Session = Depends(get_db),
):
    """
    Initiates a new quiz run with exactly 10 questions.
    1. Generates 10 fresh, unique questions via Groq Cloud AI.
    2. Falls back to randomly sampled question bank if Groq is offline or throttling.
    3. Shuffles answer options per session and server stamps question_shown_at.
    """
    num_q = payload.num_questions or 10  # Enforce 10 questions per quiz run (or test override)
    target_topic = payload.topic if payload.topic else random.choice(["Physics", "Chemistry", "Mathematics", "Biology", "Computer Science"])

    selected_questions: List[models.QuizQuestion] = []

    # 1. Attempt dynamic question generation via Groq Cloud AI
    try:
        from app.services.ai_service import generate_ai_quiz_questions
        ai_questions = _run_async(generate_ai_quiz_questions(topic=target_topic, num_questions=num_q))
        if ai_questions:
            for q_data in ai_questions:
                q = models.QuizQuestion(**q_data)
                db.add(q)
                selected_questions.append(q)
            db.commit()
            for q in selected_questions:
                db.refresh(q)
    except Exception as exc:
        # Fallback cleanly to database question bank
        pass

    # 2. Fallback to existing question bank if AI generation didn't yield full set
    if len(selected_questions) < num_q:
        from app.services.game_logic import ensure_quiz_questions_exist
        ensure_quiz_questions_exist(db)

        query = db.query(models.QuizQuestion)
        if payload.topic:
            filtered = query.filter(models.QuizQuestion.topic.ilike(f"%{payload.topic}%")).all()
            pool = filtered if filtered else query.all()
        else:
            pool = query.all()

        if pool:
            needed = num_q - len(selected_questions)
            # Pick random distinct questions not already in selected_questions
            existing_ids = {q.id for q in selected_questions if q.id}
            available = [q for q in pool if q.id not in existing_ids]
            if not available:
                available = pool
            sample_size = min(needed, len(available))
            fallback_sample = random.sample(available, sample_size)
            selected_questions.extend(fallback_sample)

    if not selected_questions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No quiz questions available. Please try again.",
        )

    num_q = len(selected_questions)
    quiz_run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    sessions: List[models.QuizSession] = []
    first_shuffled_options: List[str] = []

    for idx, q in enumerate(selected_questions):
        shuffled_options, permutation = generate_shuffled_options(q)
        q_session = models.QuizSession(
            quiz_run_id=quiz_run_id,
            user_id=current_user.id,
            question_id=q.id,
            question_index=idx,
            total_questions=num_q,
            shuffled_order=permutation_to_str(permutation),
            question_shown_at=now if idx == 0 else now,  
        )
        db.add(q_session)
        sessions.append(q_session)
        if idx == 0:
            first_shuffled_options = shuffled_options

    db.commit()
    db.refresh(sessions[0])

    q0 = selected_questions[0]
    first_q_response = QuizQuestionResponse(
        session_id=sessions[0].id,
        quiz_run_id=quiz_run_id,
        question_index=0,
        total_questions=num_q,
        prompt=sanitize_latex_to_unicode(q0.prompt),
        options=[sanitize_latex_to_unicode(o) for o in first_shuffled_options],
        preview_coins=q0.preview_coins,
        preview_xp=q0.preview_xp,
        question_shown_at=sessions[0].question_shown_at,
        topic=q0.topic,
        difficulty=q0.difficulty,
    )

    return QuizStartResponse(
        quiz_run_id=quiz_run_id,
        total_questions=num_q,
        question=first_q_response,
    )



@router.post(
    "/submit",
    response_model=QuizSubmitResponse,
    summary="Submit an answer — validated strictly via Part A safeguards",
)
def submit_answer(
    payload: QuizSubmitRequest,
    current_user: models.User = Depends(require_role("student", "admin")),
    db: Session = Depends(get_db),
):
    """
    Submits an answer to a question session.
    Gated strictly through server-side safeguards:
      1. Server answer validation
      2. Minimum cooldown check (server-recorded timestamp)
      3. Daily earn caps (reduced/reject/zero policy)
      4. Reward grant + audit log
      5. Pattern anomaly check
    """
    session = db.get(models.QuizSession, payload.session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz session not found.",
        )

    if session.user_id != current_user.id and current_user.role != models.UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This quiz session does not belong to you.",
        )

    if session.submitted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This question has already been answered.",
        )

   
    result = grant_safeguarded_reward(
        db=db,
        user_id=current_user.id,
        session=session,
        selected_shuffled_index=payload.selected_option_index,
    )

    
    run_sessions = (
        db.query(models.QuizSession)
        .filter_by(quiz_run_id=session.quiz_run_id)
        .order_by(models.QuizSession.question_index.asc())
        .all()
    )
    streak = 0
    for s in run_sessions:
        if s.submitted_at:
            if s.is_correct:
                streak += 1
            else:
                streak = 0

    # Determine correct option index in the shuffled list and resolve explanation
    perm = str_to_permutation(session.shuffled_order)
    canonical_correct = session.question.correct_option_index
    shuffled_correct_index = perm.index(canonical_correct) if canonical_correct in perm else 0
    canonical_options = session.question.get_canonical_options()
    correct_option_text = canonical_options[canonical_correct] if 0 <= canonical_correct < len(canonical_options) else ""
    correct_option_text = sanitize_latex_to_unicode(correct_option_text)

    explanation = session.question.explanation
    if not explanation:
        explanation = f"The correct answer is '{correct_option_text}'."
    explanation = sanitize_latex_to_unicode(explanation)

    wallet = db.query(models.Wallet).filter_by(user_id=current_user.id).first()

    return QuizSubmitResponse(
        is_correct=result["is_correct"],
        correct_option_index=shuffled_correct_index,
        correct_option_text=correct_option_text,
        explanation=explanation,
        coins_awarded=result["coins_awarded"],
        xp_awarded=result["xp_awarded"],
        preview_coins=session.question.preview_coins,
        preview_xp=session.question.preview_xp,
        rejection_reason=result.get("rejection_reason"),
        detail=result.get("detail"),
        wallet_balance=wallet.balance if wallet else None,
        wallet_xp=wallet.xp if wallet else None,
        streak=streak,
    )



@router.get(
    "/{quiz_run_id}/next/{question_index}",
    response_model=QuizNextResponse,
    summary="Get the next question in the current quiz run",
)
def get_next_question(
    quiz_run_id: str,
    question_index: int,
    current_user: models.User = Depends(require_role("student", "admin")),
    db: Session = Depends(get_db),
):
    """
    Fetches the question at `question_index` for this run.
    Stamps `question_shown_at` at retrieval time to ensure accurate cooldown timing.
    """
    session = (
        db.query(models.QuizSession)
        .filter_by(quiz_run_id=quiz_run_id, question_index=question_index)
        .first()
    )

    if not session:
        return QuizNextResponse(finished=True, question=None)

    if session.user_id != current_user.id and current_user.role != models.UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )


    now = datetime.now(timezone.utc)
    if session.submitted_at is None:
        session.question_shown_at = now
        db.commit()
        db.refresh(session)

   
    q = session.question
    canonical = q.get_canonical_options()
    perm = str_to_permutation(session.shuffled_order)
    shuffled_options = [canonical[i] for i in perm]

    q_response = QuizQuestionResponse(
        session_id=session.id,
        quiz_run_id=quiz_run_id,
        question_index=session.question_index,
        total_questions=session.total_questions,
        prompt=sanitize_latex_to_unicode(q.prompt),
        options=[sanitize_latex_to_unicode(o) for o in shuffled_options],
        preview_coins=q.preview_coins,
        preview_xp=q.preview_xp,
        question_shown_at=session.question_shown_at,
        topic=q.topic,
        difficulty=q.difficulty,
    )

    return QuizNextResponse(finished=False, question=q_response)



@router.get(
    "/summary/{quiz_run_id}",
    response_model=QuizSummaryResponse,
    summary="Get post-quiz summary with transparent reward breakdown & notices",
)
def get_quiz_summary(
    quiz_run_id: str,
    current_user: models.User = Depends(require_role("student", "admin")),
    db: Session = Depends(get_db),
):
    """
    Returns aggregated post-quiz summary data.
    Transparently displays any safeguards triggered (e.g. cooldown violations, daily cap reductions).
    """
    sessions = (
        db.query(models.QuizSession)
        .filter_by(quiz_run_id=quiz_run_id)
        .order_by(models.QuizSession.question_index.asc())
        .all()
    )

    if not sessions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz run not found.",
        )

    if sessions[0].user_id != current_user.id and current_user.role != models.UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
        )

    total_q = len(sessions)
    answered = sum(1 for s in sessions if s.submitted_at is not None)
    correct = sum(1 for s in sessions if s.is_correct is True)
    accuracy_pct = round((correct / answered * 100), 1) if answered > 0 else 0.0

    total_coins = sum(s.coins_awarded for s in sessions)
    total_xp = sum(s.xp_awarded for s in sessions)

    rejections = sum(1 for s in sessions if s.rejection_reason is not None)

   
    flag_count = (
        db.query(models.RewardAuditLog)
        .filter(
            models.RewardAuditLog.user_id == current_user.id,
            models.RewardAuditLog.reason_code == models.ReasonCode.pattern_flagged,
            models.RewardAuditLog.created_at >= sessions[0].question_shown_at,
        )
        .count()
    )

    notices: List[str] = []
    cooldown_count = sum(1 for s in sessions if s.rejection_reason == "cooldown_violation")
    if cooldown_count > 0:
        notices.append(
            f"⚡ {cooldown_count} answer{'s were' if cooldown_count > 1 else ' was'} submitted faster than the {settings.QUESTION_MIN_COOLDOWN_SECONDS}s minimum threshold and could not qualify for rewards."
        )

    cap_count = sum(1 for s in sessions if s.rejection_reason == "cap_exceeded")
    if cap_count > 0:
        notices.append(
            f"🛡️ Daily earn limit reached ({settings.DAILY_MAX_COINS} coins / {settings.DAILY_MAX_XP} XP). Policy: {settings.CAP_EXCEEDED_POLICY}."
        )

    answers_summary: List[QuizAnswerSummary] = [
        QuizAnswerSummary(
            question_index=s.question_index,
            prompt=s.question.prompt,
            is_correct=s.is_correct,
            coins_awarded=s.coins_awarded,
            xp_awarded=s.xp_awarded,
            rejection_reason=s.rejection_reason,
        )
        for s in sessions
    ]

    return QuizSummaryResponse(
        quiz_run_id=quiz_run_id,
        total_questions=total_q,
        answered=answered,
        correct=correct,
        accuracy_pct=accuracy_pct,
        total_coins=total_coins,
        total_xp=total_xp,
        rejections=rejections,
        flags=flag_count,
        answers=answers_summary,
        transparency_notices=notices,
    )
