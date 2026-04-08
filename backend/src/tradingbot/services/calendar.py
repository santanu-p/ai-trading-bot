from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from tradingbot.config import get_settings
from tradingbot.enums import InstrumentClass, TradingPattern
from tradingbot.models import BotSettings


@dataclass(frozen=True, slots=True)
class MarketSessionState:
    venue: str
    timezone: str
    status: str
    reason: str | None
    is_half_day: bool
    can_scan: bool
    can_submit_orders: bool
    should_flatten_positions: bool
    session_opens_at: datetime | None
    session_closes_at: datetime | None
    next_session_opens_at: datetime | None


class MarketCalendarService:
    SAME_SESSION_PATTERNS = {
        TradingPattern.SCALPING,
        TradingPattern.INTRADAY,
    }

    def __init__(self, venue: str, timezone: str, flatten_buffer_minutes: int) -> None:
        self.venue = venue.strip() or "Unknown venue"
        self.timezone = timezone.strip() or "UTC"
        self.flatten_buffer_minutes = max(flatten_buffer_minutes, 1)
        self.zone = ZoneInfo(self.timezone)

    @classmethod
    def for_settings(cls, settings_row: BotSettings) -> "MarketCalendarService":
        return cls(
            venue=settings_row.broker_venue,
            timezone=settings_row.broker_timezone,
            flatten_buffer_minutes=get_settings().intraday_flatten_buffer_minutes,
        )

    def session_state(
        self,
        *,
        trading_pattern: TradingPattern | None,
        instrument_class: InstrumentClass | None,
        at: datetime | None = None,
    ) -> MarketSessionState:
        reference = (at or datetime.now(UTC)).astimezone(self.zone)
        if self._is_us_equities():
            return self._us_equities_state(reference, trading_pattern, instrument_class)
        return self._generic_weekday_state(reference, trading_pattern, instrument_class)

    def _us_equities_state(
        self,
        reference: datetime,
        trading_pattern: TradingPattern | None,
        instrument_class: InstrumentClass | None,
    ) -> MarketSessionState:
        trading_day = reference.date()
        if self._is_market_holiday(trading_day):
            return MarketSessionState(
                venue=self.venue,
                timezone=self.timezone,
                status="closed",
                reason="Exchange holiday",
                is_half_day=False,
                can_scan=False,
                can_submit_orders=False,
                should_flatten_positions=False,
                session_opens_at=None,
                session_closes_at=None,
                next_session_opens_at=self._next_session_open(reference),
            )

        if trading_day.weekday() >= 5:
            return MarketSessionState(
                venue=self.venue,
                timezone=self.timezone,
                status="closed",
                reason="Weekend",
                is_half_day=False,
                can_scan=False,
                can_submit_orders=False,
                should_flatten_positions=False,
                session_opens_at=None,
                session_closes_at=None,
                next_session_opens_at=self._next_session_open(reference),
            )

        session_open = datetime.combine(trading_day, time(9, 30), tzinfo=self.zone)
        session_close_time = time(13, 0) if self._is_half_day(trading_day) else time(16, 0)
        session_close = datetime.combine(trading_day, session_close_time, tzinfo=self.zone)
        flatten_window_start = session_close - timedelta(minutes=self.flatten_buffer_minutes)
        same_session_strategy = self._requires_same_session_flatten(trading_pattern, instrument_class)

        if reference < session_open:
            return MarketSessionState(
                venue=self.venue,
                timezone=self.timezone,
                status="pre_open",
                reason="Market has not opened yet.",
                is_half_day=self._is_half_day(trading_day),
                can_scan=False,
                can_submit_orders=False,
                should_flatten_positions=False,
                session_opens_at=session_open.astimezone(UTC),
                session_closes_at=session_close.astimezone(UTC),
                next_session_opens_at=session_open.astimezone(UTC),
            )

        if reference >= session_close:
            return MarketSessionState(
                venue=self.venue,
                timezone=self.timezone,
                status="closed",
                reason="Session closed.",
                is_half_day=self._is_half_day(trading_day),
                can_scan=False,
                can_submit_orders=False,
                should_flatten_positions=False,
                session_opens_at=session_open.astimezone(UTC),
                session_closes_at=session_close.astimezone(UTC),
                next_session_opens_at=self._next_session_open(reference),
            )

        if same_session_strategy and reference >= flatten_window_start:
            return MarketSessionState(
                venue=self.venue,
                timezone=self.timezone,
                status="flatten_window",
                reason="Same-session strategies must flatten into the close.",
                is_half_day=self._is_half_day(trading_day),
                can_scan=False,
                can_submit_orders=False,
                should_flatten_positions=True,
                session_opens_at=session_open.astimezone(UTC),
                session_closes_at=session_close.astimezone(UTC),
                next_session_opens_at=self._next_session_open(reference),
            )

        return MarketSessionState(
            venue=self.venue,
            timezone=self.timezone,
            status="open",
            reason=None,
            is_half_day=self._is_half_day(trading_day),
            can_scan=True,
            can_submit_orders=True,
            should_flatten_positions=False,
            session_opens_at=session_open.astimezone(UTC),
            session_closes_at=session_close.astimezone(UTC),
            next_session_opens_at=self._next_session_open(reference),
        )

    def _generic_weekday_state(
        self,
        reference: datetime,
        trading_pattern: TradingPattern | None,
        instrument_class: InstrumentClass | None,
    ) -> MarketSessionState:
        trading_day = reference.date()
        if trading_day.weekday() >= 5:
            return MarketSessionState(
                venue=self.venue,
                timezone=self.timezone,
                status="closed",
                reason="Weekend",
                is_half_day=False,
                can_scan=False,
                can_submit_orders=False,
                should_flatten_positions=False,
                session_opens_at=None,
                session_closes_at=None,
                next_session_opens_at=self._next_weekday_open(reference),
            )

        session_open = datetime.combine(trading_day, time(9, 30), tzinfo=self.zone)
        session_close = datetime.combine(trading_day, time(16, 0), tzinfo=self.zone)
        flatten_window_start = session_close - timedelta(minutes=self.flatten_buffer_minutes)
        same_session_strategy = self._requires_same_session_flatten(trading_pattern, instrument_class)
        if reference < session_open:
            return MarketSessionState(
                venue=self.venue,
                timezone=self.timezone,
                status="pre_open",
                reason="Market has not opened yet.",
                is_half_day=False,
                can_scan=False,
                can_submit_orders=False,
                should_flatten_positions=False,
                session_opens_at=session_open.astimezone(UTC),
                session_closes_at=session_close.astimezone(UTC),
                next_session_opens_at=session_open.astimezone(UTC),
            )
        if reference >= session_close:
            return MarketSessionState(
                venue=self.venue,
                timezone=self.timezone,
                status="closed",
                reason="Session closed.",
                is_half_day=False,
                can_scan=False,
                can_submit_orders=False,
                should_flatten_positions=False,
                session_opens_at=session_open.astimezone(UTC),
                session_closes_at=session_close.astimezone(UTC),
                next_session_opens_at=self._next_weekday_open(reference),
            )
        if same_session_strategy and reference >= flatten_window_start:
            return MarketSessionState(
                venue=self.venue,
                timezone=self.timezone,
                status="flatten_window",
                reason="Same-session strategies must flatten into the close.",
                is_half_day=False,
                can_scan=False,
                can_submit_orders=False,
                should_flatten_positions=True,
                session_opens_at=session_open.astimezone(UTC),
                session_closes_at=session_close.astimezone(UTC),
                next_session_opens_at=self._next_weekday_open(reference),
            )
        return MarketSessionState(
            venue=self.venue,
            timezone=self.timezone,
            status="open",
            reason=None,
            is_half_day=False,
            can_scan=True,
            can_submit_orders=True,
            should_flatten_positions=False,
            session_opens_at=session_open.astimezone(UTC),
            session_closes_at=session_close.astimezone(UTC),
            next_session_opens_at=self._next_weekday_open(reference),
        )

    def _is_us_equities(self) -> bool:
        normalized = self.venue.lower()
        return "equit" in normalized and "us" in normalized

    def _requires_same_session_flatten(
        self,
        trading_pattern: TradingPattern | None,
        instrument_class: InstrumentClass | None,
    ) -> bool:
        return trading_pattern in self.SAME_SESSION_PATTERNS and instrument_class == InstrumentClass.CASH_EQUITY

    def _next_session_open(self, reference: datetime) -> datetime:
        probe = reference + timedelta(days=1)
        while probe.date().weekday() >= 5 or self._is_market_holiday(probe.date()):
            probe += timedelta(days=1)
        return datetime.combine(probe.date(), time(9, 30), tzinfo=self.zone).astimezone(UTC)

    def _next_weekday_open(self, reference: datetime) -> datetime:
        probe = reference + timedelta(days=1)
        while probe.date().weekday() >= 5:
            probe += timedelta(days=1)
        return datetime.combine(probe.date(), time(9, 30), tzinfo=self.zone).astimezone(UTC)

    def _is_market_holiday(self, value: date) -> bool:
        holidays = {
            self._observed_fixed_holiday(value.year, 1, 1),
            self._nth_weekday(value.year, 1, 0, 3),
            self._nth_weekday(value.year, 2, 0, 3),
            self._good_friday(value.year),
            self._last_weekday(value.year, 5, 0),
            self._observed_fixed_holiday(value.year, 6, 19),
            self._observed_fixed_holiday(value.year, 7, 4),
            self._nth_weekday(value.year, 9, 0, 1),
            self._nth_weekday(value.year, 11, 3, 4),
            self._observed_fixed_holiday(value.year, 12, 25),
        }
        return value in holidays

    def _is_half_day(self, value: date) -> bool:
        thanksgiving = self._nth_weekday(value.year, 11, 3, 4)
        christmas_eve = date(value.year, 12, 24)
        july_third = date(value.year, 7, 3)
        half_days = {
            thanksgiving + timedelta(days=1),
        }
        if christmas_eve.weekday() < 5 and not self._is_market_holiday(christmas_eve):
            half_days.add(christmas_eve)
        if july_third.weekday() < 5 and not self._is_market_holiday(july_third):
            half_days.add(july_third)
        return value in half_days

    def _observed_fixed_holiday(self, year: int, month: int, day: int) -> date:
        holiday = date(year, month, day)
        if holiday.weekday() == 5:
            return holiday - timedelta(days=1)
        if holiday.weekday() == 6:
            return holiday + timedelta(days=1)
        return holiday

    def _nth_weekday(self, year: int, month: int, weekday: int, occurrence: int) -> date:
        first = date(year, month, 1)
        offset = (weekday - first.weekday()) % 7
        return first + timedelta(days=offset + (occurrence - 1) * 7)

    def _last_weekday(self, year: int, month: int, weekday: int) -> date:
        if month == 12:
            probe = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            probe = date(year, month + 1, 1) - timedelta(days=1)
        while probe.weekday() != weekday:
            probe -= timedelta(days=1)
        return probe

    def _good_friday(self, year: int) -> date:
        easter = self._easter_sunday(year)
        return easter - timedelta(days=2)

    def _easter_sunday(self, year: int) -> date:
        a = year % 19
        b = year // 100
        c = year % 100
        d = b // 4
        e = b % 4
        f = (b + 8) // 25
        g = (b - f + 1) // 3
        h = (19 * a + b - d - g + 15) % 30
        i = c // 4
        k = c % 4
        l = (32 + 2 * e + 2 * i - h - k) % 7
        m = (a + 11 * h + 22 * l) // 451
        month = (h + l - 7 * m + 114) // 31
        day = ((h + l - 7 * m + 114) % 31) + 1
        return date(year, month, day)
