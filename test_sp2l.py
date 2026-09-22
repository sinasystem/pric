import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

from models.candle import Candle
from strategies.key_bar import KeyBarEvent
from strategies.p_gap import PGapEvent
from strategies.pullback_structure import (
    PullbackStructureEvent,
    PullbackStructureStatus,
)
from strategies.second_leg import SecondLegEvent
from strategies.signal_bar import SignalBarEvent
from strategies.sp2l import SP2LStateMachine
from strategies.sp2l_candidate import SP2LCandidate
from strategies.sp2l_state import SP2LSetup, SP2LState
from strategies.spike_event import SpikeEvent
from strategies.spike_measurements import SpikeMeasurements
from strategies.structure import StructurePoint


BASE_TIME = datetime(2026, 1, 1, 10, 0)


def make_candle(
    minute: int,
    open_price: float = 100.0,
    high: float = 101.0,
    low: float = 99.0,
    close: float = 100.5,
) -> Candle:
    return Candle(
        timestamp=BASE_TIME + timedelta(minutes=minute),
        open=open_price,
        high=high,
        low=low,
        close=close,
    )


def make_spike(candle: Candle) -> SpikeEvent:
    measurements = SpikeMeasurements(
        direction="buy",
        total_range=2.0,
        body=1.5,
        upper_wick=0.2,
        lower_wick=0.3,
        body_ratio_of_range=0.75,
        closing_wick_ratio=0.10,
        average_previous_range=1.0,
        average_previous_body=0.8,
        range_ratio=2.0,
        body_ratio=1.875,
        previous_high=99.0,
        previous_low=98.0,
        high_breakout_distance=2.0,
        low_breakout_distance=0.0,
        close_breakout_distance=1.5,
        is_spike=True,
        breakout_distance=1.5,
    )

    return SpikeEvent(
        breakout_candle=candle,
        direction="buy",
        measurements=measurements,
    )


def make_p_gap(
    spike: SpikeEvent,
    pre_breakout: Candle,
    follow_through: Candle,
) -> PGapEvent:
    return PGapEvent(
        direction="buy",
        pre_breakout_candle=pre_breakout,
        breakout_candle=spike.breakout_candle,
        follow_through_candle=follow_through,
    )


def make_second_leg(
    p_gap: PGapEvent,
    reference: Candle,
    anchor: Candle,
) -> SecondLegEvent:
    return SecondLegEvent(
        direction="buy",
        p_gap=p_gap,
        pullback_candle=anchor,
        reference_candle=reference,
    )


def make_pullback_structure(
    second_leg: SecondLegEvent,
    anchor: Candle,
) -> PullbackStructureEvent:
    structure_points = [
        StructurePoint(
            type="lower_high",
            candle=make_candle(
                25,
                open_price=99.0,
                high=100.0,
                low=98.5,
                close=99.5,
            ),
            price=100.0,
        ),
        StructurePoint(
            type="lower_high",
            candle=make_candle(
                30,
                open_price=98.5,
                high=99.5,
                low=97.8,
                close=99.0,
            ),
            price=99.5,
        ),
        StructurePoint(
            type="lower_high",
            candle=make_candle(
                35,
                open_price=98.0,
                high=99.0,
                low=97.2,
                close=98.5,
            ),
            price=99.0,
        ),
    ]

    return PullbackStructureEvent(
        direction="buy",
        second_leg=second_leg,
        anchor_candle=anchor,
        structure_points=structure_points,
    )


def make_signal_bar(
    pullback_structure: PullbackStructureEvent,
    candle: Candle,
) -> SignalBarEvent:
    return SignalBarEvent(
        direction="buy",
        pullback_structure=pullback_structure,
        signal_candle=candle,
    )


def make_key_bar(
    signal_bar: SignalBarEvent,
    candle: Candle,
) -> KeyBarEvent:
    return KeyBarEvent(
        direction="buy",
        signal_bar=signal_bar,
        key_candle=candle,
    )


class TestSP2LStateMachine(unittest.TestCase):

    def setUp(self):
        self.spike_detector = Mock()
        self.spike_detector.config = SimpleNamespace(
            lookback=2
        )

        self.p_gap_detector = Mock()
        self.second_leg_detector = Mock()
        self.pullback_structure_detector = Mock()
        self.signal_bar_detector = Mock()
        self.key_bar_detector = Mock()
        self.swing_processor = Mock()

        self.machine = SP2LStateMachine(
            spike_detector=self.spike_detector,
            p_gap_detector=self.p_gap_detector,
            second_leg_detector=self.second_leg_detector,
            pullback_structure_detector=(
                self.pullback_structure_detector
            ),
            signal_bar_detector=self.signal_bar_detector,
            key_bar_detector=self.key_bar_detector,
            swing_processor=self.swing_processor,
        )

    def _configure_spike_for_candle(
        self,
        spike_candle: Candle,
        spike: SpikeEvent,
    ):
        def detect_event(candles):
            if candles[-1] is spike_candle:
                return spike

            return None

        self.spike_detector.detect_event.side_effect = detect_event

    def _enter_spike_validated(self):
        candle_0 = make_candle(0)
        candle_1 = make_candle(5)
        spike_candle = make_candle(10)

        spike = make_spike(spike_candle)

        self._configure_spike_for_candle(
            spike_candle,
            spike,
        )

        self.machine.process(candle_0)
        self.machine.process(candle_1)
        self.machine.process(spike_candle)

        self.assertEqual(
            len(self.machine.candidates),
            1,
        )

        candidate = self.machine.candidates[0]

        return (
            candle_1,
            spike_candle,
            spike,
            candidate,
        )

    def _enter_pullback(self):
        (
            pre_breakout,
            spike_candle,
            spike,
            candidate,
        ) = self._enter_spike_validated()

        follow_through = make_candle(15)

        p_gap = make_p_gap(
            spike=spike,
            pre_breakout=pre_breakout,
            follow_through=follow_through,
        )

        self.p_gap_detector.detect.return_value = p_gap

        self.machine.process(follow_through)

        self.assertEqual(
            len(self.machine.candidates),
            1,
        )

        candidate = self.machine.candidates[0]

        return (
            pre_breakout,
            spike_candle,
            follow_through,
            spike,
            p_gap,
            candidate,
        )

    def _enter_compression(self):
        (
            pre_breakout,
            spike_candle,
            follow_through,
            spike,
            p_gap,
            candidate,
        ) = self._enter_pullback()

        anchor = make_candle(
            20,
            open_price=102.0,
            high=103.0,
            low=100.0,
            close=101.5,
        )

        second_leg = make_second_leg(
            p_gap=p_gap,
            reference=follow_through,
            anchor=anchor,
        )

        self.second_leg_detector.detect.return_value = (
            second_leg
        )

        self.machine.process(anchor)

        self.assertEqual(
            len(self.machine.candidates),
            1,
        )

        candidate = self.machine.candidates[0]

        structure_candle = make_candle(40)

        pullback_structure = make_pullback_structure(
            second_leg=second_leg,
            anchor=anchor,
        )

        self.pullback_structure_detector.detect.return_value = (
            pullback_structure
        )

        # A compression test should not accidentally create
        # a Signal Bar through Mock's default return value.
        self.signal_bar_detector.detect.return_value = None

        self.machine.process(structure_candle)

        return (
            pre_breakout,
            spike_candle,
            follow_through,
            anchor,
            structure_candle,
            spike,
            p_gap,
            second_leg,
            pullback_structure,
            candidate,
        )

    def test_starts_with_no_candidates(self):
        self.assertEqual(
            self.machine.candidates,
            [],
        )

    def test_no_spike_keeps_candidate_collection_empty(self):
        self.spike_detector.detect_event.return_value = None

        self.machine.process(make_candle(0))
        self.machine.process(make_candle(5))
        self.machine.process(make_candle(10))

        self.assertEqual(
            self.machine.candidates,
            [],
        )

    def test_spike_creates_spike_validated_candidate(self):
        candle_1, spike_candle, spike, candidate = (
            self._enter_spike_validated()
        )

        self.assertEqual(
            candidate.state,
            SP2LState.SPIKE_VALIDATED,
        )

        self.assertIs(
            candidate.pending_spike,
            spike,
        )

        self.assertIs(
            candidate.pre_breakout_candle,
            candle_1,
        )

    def test_failed_p_gap_removes_candidate(self):
        self._enter_spike_validated()

        self.p_gap_detector.detect.return_value = None

        self.machine.process(make_candle(15))

        self.assertEqual(
            self.machine.candidates,
            [],
        )

    def test_valid_p_gap_moves_candidate_to_pullback(self):
        (
            pre_breakout,
            _,
            follow_through,
            spike,
            p_gap,
            candidate,
        ) = self._enter_pullback()

        self.assertEqual(
            candidate.state,
            SP2LState.PULLBACK,
        )

        self.assertIs(
            candidate.p_gap,
            p_gap,
        )

        self.p_gap_detector.detect.assert_called_once_with(
            spike_event=spike,
            pre_breakout_candle=pre_breakout,
            follow_through_candle=follow_through,
        )

    def test_second_leg_creates_anchor(self):
        (
            _,
            _,
            follow_through,
            _,
            p_gap,
            candidate,
        ) = self._enter_pullback()

        anchor = make_candle(
            20,
            open_price=102.0,
            high=103.0,
            low=100.0,
            close=101.5,
        )

        second_leg = make_second_leg(
            p_gap=p_gap,
            reference=follow_through,
            anchor=anchor,
        )

        self.second_leg_detector.detect.return_value = (
            second_leg
        )

        self.machine.process(anchor)

        candidate = self.machine.candidates[0]

        self.assertEqual(
            candidate.state,
            SP2LState.PULLBACK,
        )

        self.assertIs(
            candidate.second_leg,
            second_leg,
        )

        self.second_leg_detector.detect.assert_called_once_with(
            p_gap_event=p_gap,
            reference_candle=follow_through,
            pullback_candle=anchor,
        )

    def test_valid_pullback_structure_moves_to_compression(self):
        (
            _,
            _,
            _,
            _,
            _,
            _,
            _,
            second_leg,
            pullback_structure,
            candidate,
        ) = self._enter_compression()

        self.assertEqual(
            candidate.state,
            SP2LState.COMPRESSION_VALID,
        )

        self.assertIs(
            candidate.pullback_structure,
            pullback_structure,
        )

        self.assertIs(
            candidate.pullback_structure.second_leg,
            second_leg,
        )

        self.pullback_structure_detector.detect.assert_called_once()

    def test_compression_violation_returns_to_pullback(self):
        (
            _,
            _,
            _,
            _,
            _,
            _,
            _,
            second_leg,
            _,
            candidate,
        ) = self._enter_compression()

        self.assertEqual(
            candidate.state,
            SP2LState.COMPRESSION_VALID,
        )

        violating_candle = make_candle(
            45,
            open_price=101.0,
            high=102.0,
            low=99.0,
            close=100.0,
        )

        self.pullback_structure_detector.detect.return_value = None

        self.machine.process(violating_candle)

        candidate = self.machine.candidates[0]

        self.assertEqual(
            candidate.state,
            SP2LState.PULLBACK,
        )

        self.assertIs(
            candidate.second_leg,
            second_leg,
        )

        self.assertIsNone(
            candidate.pullback_structure,
        )

    def test_anchor_invalidation_removes_candidate(self):
        (
            _,
            _,
            follow_through,
            _,
            p_gap,
            candidate,
        ) = self._enter_pullback()

        anchor = make_candle(
            20,
            open_price=102.0,
            high=103.0,
            low=100.0,
            close=101.5,
        )

        second_leg = make_second_leg(
            p_gap=p_gap,
            reference=follow_through,
            anchor=anchor,
        )

        candidate.second_leg = second_leg

        invalidating_candle = make_candle(
            25,
            open_price=102.0,
            high=103.1,
            low=100.5,
            close=102.5,
        )

        self.machine.process(invalidating_candle)

        self.assertEqual(
            self.machine.candidates,
            [],
        )

    def test_non_anchor_violation_keeps_pullback_alive(self):
        (
            _,
            _,
            follow_through,
            _,
            p_gap,
            candidate,
        ) = self._enter_pullback()

        anchor = make_candle(
            20,
            open_price=102.0,
            high=103.0,
            low=100.0,
            close=101.5,
        )

        second_leg = make_second_leg(
            p_gap=p_gap,
            reference=follow_through,
            anchor=anchor,
        )

        candidate.second_leg = second_leg

        violating_candle = make_candle(
            25,
            open_price=101.0,
            high=102.0,
            low=99.0,
            close=100.0,
        )

        self.pullback_structure_detector.detect.return_value = None

        self.machine.process(violating_candle)

        candidate = self.machine.candidates[0]

        self.assertEqual(
            candidate.state,
            SP2LState.PULLBACK,
        )

        self.assertIs(
            candidate.second_leg,
            second_leg,
        )

        new_sequence_candle = make_candle(
            30,
            open_price=99.0,
            high=101.0,
            low=97.0,
            close=100.0,
        )

        pullback_structure = make_pullback_structure(
            second_leg=second_leg,
            anchor=anchor,
        )

        self.pullback_structure_detector.detect.return_value = (
            pullback_structure
        )

        self.machine.process(new_sequence_candle)

        candidate = self.machine.candidates[0]

        self.assertEqual(
            candidate.state,
            SP2LState.COMPRESSION_VALID,
        )

        self.assertIs(
            candidate.pullback_structure,
            pullback_structure,
        )

    def test_maximum_structure_points_invalidates_candidate(self):
        (
            _,
            _,
            follow_through,
            _,
            p_gap,
            candidate,
        ) = self._enter_pullback()

        anchor = make_candle(
            20,
            open_price=102.0,
            high=103.0,
            low=100.0,
            close=101.5,
        )

        second_leg = make_second_leg(
            p_gap=p_gap,
            reference=follow_through,
            anchor=anchor,
        )

        candidate.second_leg = second_leg

        invalidating_candle = make_candle(
            40,
            open_price=98.0,
            high=97.5,
            low=96.0,
            close=97.0,
        )

        self.pullback_structure_detector.detect.return_value = (
            PullbackStructureEvent(
                direction=second_leg.direction,
                second_leg=second_leg,
                anchor_candle=anchor,
                structure_points=[],
                status=PullbackStructureStatus.MAXIMUM_EXCEEDED,
            )
        )

        self.machine.process(invalidating_candle)

        self.assertEqual(
            self.machine.candidates,
            [],
        )

    def test_signal_bar_moves_to_waiting_for_key_bar(self):
        (
            _,
            _,
            _,
            _,
            _,
            _,
            _,
            _,
            pullback_structure,
            candidate,
        ) = self._enter_compression()

        signal_candle = make_candle(45)

        signal_bar = make_signal_bar(
            pullback_structure,
            signal_candle,
        )

        self.signal_bar_detector.detect.return_value = (
            signal_bar
        )

        self.machine.process(signal_candle)

        candidate = self.machine.candidates[0]

        self.assertEqual(
            candidate.state,
            SP2LState.WAITING_FOR_KEY_BAR,
        )

        self.assertIs(
            candidate.signal_bar,
            signal_bar,
        )

    def test_failed_key_bar_re_evaluates_structure(self):
        (
            _,
            _,
            _,
            _,
            _,
            _,
            _,
            second_leg,
            pullback_structure,
            candidate,
        ) = self._enter_compression()

        signal_candle = make_candle(45)

        signal_bar = make_signal_bar(
            pullback_structure,
            signal_candle,
        )

        self.signal_bar_detector.detect.return_value = (
            signal_bar
        )

        self.machine.process(signal_candle)

        candidate = self.machine.candidates[0]

        self.key_bar_detector.detect.return_value = None
        replacement_structure = make_pullback_structure(
            second_leg=second_leg,
            anchor=pullback_structure.anchor_candle,
        )

        self.pullback_structure_detector.detect.return_value = (
            replacement_structure
        )

        result = self.machine.process(
            make_candle(50)
        )

        self.assertEqual(
            result,
            [],
        )

        candidate = self.machine.candidates[0]

        self.assertEqual(
            candidate.state,
            SP2LState.COMPRESSION_VALID,
        )

        self.assertIsNone(
            candidate.signal_bar,
        )

        self.assertIs(
            candidate.pullback_structure,
            replacement_structure,
        )

    def test_valid_key_bar_returns_complete_setup(self):
        (
            _,
            _,
            _,
            _,
            _,
            spike,
            p_gap,
            _,
            pullback_structure,
            candidate,
        ) = self._enter_compression()

        signal_candle = make_candle(45)
        key_candle = make_candle(50)

        signal_bar = make_signal_bar(
            pullback_structure,
            signal_candle,
        )

        key_bar = make_key_bar(
            signal_bar,
            key_candle,
        )

        self.signal_bar_detector.detect.return_value = (
            signal_bar
        )
        self.key_bar_detector.detect.return_value = (
            key_bar
        )

        self.machine.process(signal_candle)

        result = self.machine.process(key_candle)

        self.assertEqual(
            len(result),
            1,
        )

        setup = result[0]

        self.assertIsInstance(
            setup,
            SP2LSetup,
        )

        self.assertEqual(
            setup.direction,
            "buy",
        )

        self.assertIs(
            setup.spike,
            spike,
        )

        self.assertIs(
            setup.p_gap,
            p_gap,
        )

        self.assertIs(
            setup.pullback_structure,
            pullback_structure,
        )

        self.assertIs(
            setup.signal_bar,
            signal_bar,
        )

        self.assertIs(
            setup.key_bar,
            key_bar,
        )

        self.assertEqual(
            self.machine.candidates,
            [],
        )

    def test_confirmed_key_bar_produces_only_one_setup(self):
        signal_bar = Mock(spec=SignalBarEvent)
        spike = Mock(spec=SpikeEvent)
        p_gap = Mock(spec=PGapEvent)
        pullback_structure = Mock(
            spec=PullbackStructureEvent
        )

        self.spike_detector.detect_event.return_value = None

        self.machine._candidates.append(
            SP2LCandidate(
                state=SP2LState.WAITING_FOR_KEY_BAR,
                pending_spike=spike,
                pre_breakout_candle=make_candle(40),
                p_gap=p_gap,
                pullback_structure=pullback_structure,
                signal_bar=signal_bar,
            )
        )

        key_bar = Mock(spec=KeyBarEvent)
        key_bar.direction = "buy"

        self.key_bar_detector.detect.return_value = key_bar

        first_result = self.machine.process(
            make_candle(45)
        )

        second_result = self.machine.process(
            make_candle(50)
        )

        self.assertEqual(
            len(first_result),
            1,
        )

        self.assertIsInstance(
            first_result[0],
            SP2LSetup,
        )

        self.assertEqual(
            second_result,
            [],
        )

        self.assertEqual(
            self.machine.candidates,
            [],
        )

    def test_state_machine_never_executes_a_trade(self):
        result = self.machine.process(
            make_candle(0)
        )

        self.assertEqual(
            result,
            [],
        )

        self.assertFalse(
            hasattr(self.machine, "account")
        )

        self.assertFalse(
            hasattr(self.machine, "risk_manager")
        )

        self.assertFalse(
            hasattr(self.machine, "pending_order")
        )

    def test_new_setup_can_form_after_maximum_structure_invalidation(self):
        (
            _,
            _,
            follow_through,
            _,
            p_gap,
            first_candidate,
        ) = self._enter_pullback()

        first_anchor = make_candle(
            20,
            open_price=102.0,
            high=103.0,
            low=100.0,
            close=101.5,
        )

        first_second_leg = make_second_leg(
            p_gap=p_gap,
            reference=follow_through,
            anchor=first_anchor,
        )

        first_candidate.second_leg = first_second_leg

        eighth_candle = make_candle(
            40,
            open_price=98.0,
            high=97.5,
            low=96.0,
            close=97.0,
        )

        self.pullback_structure_detector.detect.return_value = (
            PullbackStructureEvent(
                direction="buy",
                second_leg=first_second_leg,
                anchor_candle=first_anchor,
                structure_points=[],
                status=PullbackStructureStatus.MAXIMUM_EXCEEDED,
            )
        )

        self.machine.process(eighth_candle)

        self.assertEqual(
            self.machine.candidates,
            [],
        )

        new_candles = [
            make_candle(
                41,
                open_price=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
            ),
            make_candle(
                42,
                open_price=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
            ),
            make_candle(
                43,
                open_price=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
            ),
            make_candle(
                44,
                open_price=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
            ),
            make_candle(
                45,
                open_price=100.0,
                high=104.0,
                low=99.0,
                close=103.5,
            ),
        ]

        new_spike = make_spike(new_candles[-1])

        self._configure_spike_for_candle(
            new_candles[-1],
            new_spike,
        )

        for candle in new_candles:
            self.machine.process(candle)

        self.assertEqual(
            len(self.machine.candidates),
            1,
        )

        new_candidate = self.machine.candidates[0]

        self.assertEqual(
            new_candidate.state,
            SP2LState.SPIKE_VALIDATED,
        )

        self.assertIs(
            new_candidate.pending_spike,
            new_spike,
        )

        self.assertIs(
            new_candidate.pending_spike.breakout_candle,
            new_candles[-1],
        )

    def test_multiple_candidates_can_exist_independently(self):
        first_spike_candle = make_candle(10)
        second_spike_candle = make_candle(20)

        first_spike = make_spike(first_spike_candle)
        second_spike = make_spike(second_spike_candle)

        def detect_event(candles):
            if candles[-1] is first_spike_candle:
                return first_spike

            if candles[-1] is second_spike_candle:
                return second_spike

            return None

        self.spike_detector.detect_event.side_effect = detect_event

        self.machine.process(make_candle(0))
        self.machine.process(make_candle(5))
        self.machine.process(first_spike_candle)

        self.assertEqual(
            len(self.machine.candidates),
            1,
        )

        first_candidate = self.machine.candidates[0]

        self.machine.process(make_candle(15))

        self.assertEqual(
            len(self.machine.candidates),
            1,
        )

        self.machine.process(second_spike_candle)

        self.assertEqual(
            len(self.machine.candidates),
            2,
        )

        self.assertIs(
            self.machine.candidates[0].pending_spike,
            first_spike,
        )

        self.assertIs(
            self.machine.candidates[1].pending_spike,
            second_spike,
        )

        self.assertIs(
            self.machine.candidates[0],
            first_candidate,
        )