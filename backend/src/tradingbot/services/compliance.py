"""Compliance and audit reporting service.

Provides:
- Automated daily trade report generation (P&L, fills, rejections, risk events)
- Pattern day-trader (PDT) rule detection
- Wash-sale detection across symbols and timeframes
- Position limit monitoring
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from tradingbot.enums import OrderStatus
from tradingbot.models import (
    AuditLog,
    OrderRecord,
    PositionRecord,
    RiskEvent,
    TradeReview,
)
from tradingbot.services.metrics import observe_counter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class DailyTradeReport:
    """Automated daily trade report."""

    report_date: datetime
    profile_id: int | None
    total_trades: int
    winning_trades: int
    losing_trades: int
    total_pnl: float
    gross_profit: float
    gross_loss: float
    win_rate: float
    total_filled_orders: int
    total_rejected_orders: int
    total_canceled_orders: int
    risk_events: int
    max_single_loss: float
    max_single_win: float
    symbols_traded: list[str] = field(default_factory=list)
    pdt_warning: bool = False
    wash_sale_warnings: list[dict[str, Any]] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "report_date": self.report_date.isoformat(),
            "profile_id": self.profile_id,
            "summary": {
                "total_trades": self.total_trades,
                "winning_trades": self.winning_trades,
                "losing_trades": self.losing_trades,
                "win_rate": round(self.win_rate, 4),
            },
            "pnl": {
                "total_pnl": round(self.total_pnl, 2),
                "gross_profit": round(self.gross_profit, 2),
                "gross_loss": round(self.gross_loss, 2),
                "max_single_win": round(self.max_single_win, 2),
                "max_single_loss": round(self.max_single_loss, 2),
            },
            "orders": {
                "filled": self.total_filled_orders,
                "rejected": self.total_rejected_orders,
                "canceled": self.total_canceled_orders,
            },
            "risk_events": self.risk_events,
            "symbols_traded": self.symbols_traded,
            "compliance": {
                "pdt_warning": self.pdt_warning,
                "wash_sale_warnings": self.wash_sale_warnings,
            },
        }


@dataclass(slots=True)
class PDTCheckResult:
    """Result of a Pattern Day Trader check."""

    is_pdt: bool
    day_trades_count: int
    day_trades_limit: int
    rolling_window_days: int
    day_trade_details: list[dict[str, Any]] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "is_pdt": self.is_pdt,
            "day_trades_count": self.day_trades_count,
            "day_trades_limit": self.day_trades_limit,
            "rolling_window_days": self.rolling_window_days,
            "day_trade_details": self.day_trade_details,
        }


@dataclass(slots=True)
class WashSaleResult:
    """Result of a wash-sale check for a symbol."""

    symbol: str
    is_wash_sale: bool
    sell_date: datetime | None
    repurchase_date: datetime | None
    days_between: int
    disallowed_loss: float

    def to_payload(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "is_wash_sale": self.is_wash_sale,
            "sell_date": self.sell_date.isoformat() if self.sell_date else None,
            "repurchase_date": self.repurchase_date.isoformat()
            if self.repurchase_date
            else None,
            "days_between": self.days_between,
            "disallowed_loss": round(self.disallowed_loss, 2),
        }


def _review_datetime(review: TradeReview, key: str) -> datetime | None:
    value = review.review_payload.get(key)
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    if key == "entry_time":
        return review.created_at
    if key == "exit_time":
        return review.reviewed_at or review.created_at
    return None


# ---------------------------------------------------------------------------
# Compliance service
# ---------------------------------------------------------------------------
class ComplianceService:
    """Compliance and audit reporting service."""

    def __init__(
        self,
        session: Session,
        *,
        profile_id: int | None = None,
    ) -> None:
        self.session = session
        self.profile_id = profile_id

    def generate_daily_report(
        self,
        *,
        date: datetime | None = None,
    ) -> DailyTradeReport:
        """Generate a comprehensive daily trade report."""
        as_of = date or datetime.now(UTC)
        start_of_day = as_of.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        # Trade reviews (completed trades)
        reviews_query = select(TradeReview).where(
            TradeReview.created_at >= start_of_day,
            TradeReview.created_at < end_of_day,
        )
        if self.profile_id is not None:
            reviews_query = reviews_query.where(
                TradeReview.profile_id == self.profile_id
            )
        reviews = list(self.session.scalars(reviews_query).all())

        winning = [r for r in reviews if r.pnl >= 0]
        losing = [r for r in reviews if r.pnl < 0]
        gross_profit = sum(r.pnl for r in winning)
        gross_loss = sum(r.pnl for r in losing)
        symbols = list(set(r.symbol for r in reviews))

        # Order stats
        orders_query = select(OrderRecord).where(
            OrderRecord.created_at >= start_of_day,
            OrderRecord.created_at < end_of_day,
        )
        if self.profile_id is not None:
            orders_query = orders_query.where(OrderRecord.profile_id == self.profile_id)
        orders = list(self.session.scalars(orders_query).all())

        filled = sum(1 for o in orders if o.status == OrderStatus.FILLED)
        rejected = sum(1 for o in orders if o.status == OrderStatus.REJECTED)
        canceled = sum(1 for o in orders if o.status == OrderStatus.CANCELED)

        # Risk events
        risk_query = (
            select(func.count())
            .select_from(RiskEvent)
            .where(
                RiskEvent.created_at >= start_of_day,
                RiskEvent.created_at < end_of_day,
            )
        )
        if self.profile_id is not None:
            risk_query = risk_query.where(RiskEvent.profile_id == self.profile_id)
        risk_count = int(self.session.scalar(risk_query) or 0)

        # PDT check
        pdt = self.check_pdt_status()

        # Wash sale check
        wash_sales = self.check_wash_sales()
        wash_warnings = [ws.to_payload() for ws in wash_sales if ws.is_wash_sale]

        total = len(reviews)
        report = DailyTradeReport(
            report_date=as_of,
            profile_id=self.profile_id,
            total_trades=total,
            winning_trades=len(winning),
            losing_trades=len(losing),
            total_pnl=gross_profit + gross_loss,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            win_rate=(len(winning) / max(total, 1)),
            total_filled_orders=filled,
            total_rejected_orders=rejected,
            total_canceled_orders=canceled,
            risk_events=risk_count,
            max_single_loss=min((r.pnl for r in reviews), default=0.0),
            max_single_win=max((r.pnl for r in reviews), default=0.0),
            symbols_traded=symbols,
            pdt_warning=pdt.is_pdt,
            wash_sale_warnings=wash_warnings,
        )

        # Audit log
        self.session.add(
            AuditLog(
                profile_id=self.profile_id,
                action="compliance.daily_report_generated",
                actor="system",
                actor_role="system",
                details={
                    "date": as_of.isoformat(),
                    "total_trades": total,
                    "pnl": report.total_pnl,
                },
            )
        )
        observe_counter("compliance.daily_report_generated")
        return report

    def check_pdt_status(
        self,
        *,
        window_days: int = 5,
        day_trade_limit: int = 3,
    ) -> PDTCheckResult:
        """Check for Pattern Day Trader violations.

        A day trade is defined as buying and selling (or selling short and
        buying to cover) the same security on the same trading day.
        FINRA rule: 4+ day trades in 5 business days with < $25k equity.
        """
        cutoff = datetime.now(UTC) - timedelta(days=window_days)

        # Get recent completed trades grouped by symbol and date
        reviews_query = (
            select(TradeReview)
            .where(TradeReview.created_at >= cutoff)
            .order_by(TradeReview.created_at)
        )
        if self.profile_id is not None:
            reviews_query = reviews_query.where(
                TradeReview.profile_id == self.profile_id
            )
        reviews = list(self.session.scalars(reviews_query).all())

        # Detect day trades: same symbol, opened and closed on same calendar day
        day_trades: list[dict[str, Any]] = []
        seen: dict[tuple[str, str], bool] = {}

        for review in reviews:
            entry_time = _review_datetime(review, "entry_time")
            exit_time = _review_datetime(review, "exit_time")
            if entry_time and exit_time:
                entry_date = (
                    entry_time.date() if hasattr(entry_time, "date") else entry_time
                )
                exit_date = (
                    exit_time.date() if hasattr(exit_time, "date") else exit_time
                )
                if entry_date == exit_date:
                    key = (review.symbol, str(entry_date))
                    if key not in seen:
                        seen[key] = True
                        day_trades.append(
                            {
                                "symbol": review.symbol,
                                "date": str(entry_date),
                                "pnl": round(review.pnl, 2),
                            }
                        )

        is_pdt = len(day_trades) >= day_trade_limit
        if is_pdt:
            observe_counter("compliance.pdt_warning")

        return PDTCheckResult(
            is_pdt=is_pdt,
            day_trades_count=len(day_trades),
            day_trades_limit=day_trade_limit,
            rolling_window_days=window_days,
            day_trade_details=day_trades,
        )

    def check_wash_sales(
        self,
        *,
        window_days: int = 30,
    ) -> list[WashSaleResult]:
        """Detect potential wash sales across symbols.

        IRS wash-sale rule: Cannot deduct a loss if the same or
        substantially identical security is purchased within 30 days
        before or after the sale at a loss.
        """
        cutoff = datetime.now(UTC) - timedelta(days=window_days * 2)

        reviews_query = (
            select(TradeReview)
            .where(TradeReview.created_at >= cutoff)
            .order_by(TradeReview.created_at)
        )
        if self.profile_id is not None:
            reviews_query = reviews_query.where(
                TradeReview.profile_id == self.profile_id
            )
        reviews = list(self.session.scalars(reviews_query).all())

        # Group by symbol
        by_symbol: dict[str, list[TradeReview]] = {}
        for r in reviews:
            by_symbol.setdefault(r.symbol, []).append(r)

        results: list[WashSaleResult] = []
        for symbol, trades in by_symbol.items():
            loss_trades = [
                t for t in trades if t.pnl < 0 and _review_datetime(t, "exit_time")
            ]
            buy_trades = [t for t in trades if _review_datetime(t, "entry_time")]

            for loss_trade in loss_trades:
                sell_date = _review_datetime(loss_trade, "exit_time")
                if sell_date is None:
                    continue

                for buy_trade in buy_trades:
                    if buy_trade == loss_trade:
                        continue
                    buy_date = _review_datetime(buy_trade, "entry_time")
                    if buy_date is None:
                        continue

                    days_diff = abs((buy_date - sell_date).days)
                    if days_diff <= window_days:
                        results.append(
                            WashSaleResult(
                                symbol=symbol,
                                is_wash_sale=True,
                                sell_date=sell_date,
                                repurchase_date=buy_date,
                                days_between=days_diff,
                                disallowed_loss=abs(loss_trade.pnl),
                            )
                        )
                        observe_counter(
                            "compliance.wash_sale_detected", tags={"symbol": symbol}
                        )
                        break  # One match per loss trade is enough

        return results

    def check_position_limits(
        self,
        *,
        max_single_position_pct: float = 15.0,
        max_sector_pct: float = 40.0,
        portfolio_equity: float = 100_000.0,
    ) -> list[dict[str, Any]]:
        """Check portfolio positions against concentration limits."""
        positions_query = select(PositionRecord).where(PositionRecord.quantity > 0)
        if self.profile_id is not None:
            positions_query = positions_query.where(
                PositionRecord.profile_id == self.profile_id
            )
        positions = list(self.session.scalars(positions_query).all())

        violations: list[dict[str, Any]] = []
        for pos in positions:
            market_value = abs(
                float(pos.quantity or 0) * float(pos.average_entry_price or 0)
            )
            position_pct = (market_value / max(portfolio_equity, 1.0)) * 100
            if position_pct > max_single_position_pct:
                violations.append(
                    {
                        "type": "single_position_limit",
                        "symbol": pos.symbol,
                        "position_pct": round(position_pct, 2),
                        "limit_pct": max_single_position_pct,
                        "market_value": round(market_value, 2),
                    }
                )
                observe_counter(
                    "compliance.position_limit_violation", tags={"symbol": pos.symbol}
                )

        return violations
