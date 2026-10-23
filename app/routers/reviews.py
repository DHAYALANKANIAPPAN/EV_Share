from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from ..deps import DB, CurrentUser
from ..models import Booking, BookingStatus, Charger, Review, utcnow
from ..schemas import ReviewCreate, ReviewOut

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.post("", response_model=ReviewOut, status_code=status.HTTP_201_CREATED)
def create_review(body: ReviewCreate, db: DB, user: CurrentUser):
    booking = db.get(Booking, body.booking_id)
    if not booking or booking.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Booking not found")
    if booking.status != BookingStatus.CONFIRMED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cancelled bookings cannot be reviewed")
    if booking.end_time > utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You can review a charger after your booking has ended")
    if booking.review:
        raise HTTPException(status.HTTP_409_CONFLICT, "You already reviewed this booking")
    review = Review(booking_id=booking.id, charger_id=booking.charger_id, user_id=user.id,
                    rating=body.rating, comment=(body.comment or "").strip() or None)
    db.add(review)
    db.commit()
    return review


@router.get("/charger/{charger_id}", response_model=list[ReviewOut])
def charger_reviews(charger_id: int, db: DB):
    if not db.get(Charger, charger_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Charger not found")
    return db.scalars(select(Review).where(Review.charger_id == charger_id).order_by(Review.id.desc())).all()
