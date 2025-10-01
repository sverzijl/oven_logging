"""
State-of-the-art fuzzy logic algorithm for detecting baking curve boundaries.

This module implements a sophisticated fuzzy inference system that evaluates
multiple temperature signals simultaneously to detect the start and end points
of baking curves with high accuracy and confidence scoring.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class FuzzyDetectionResult:
    """Result from fuzzy curve detection."""
    start_idx: int
    end_idx: int
    start_confidence: float  # 0.0-1.0
    end_confidence: float    # 0.0-1.0
    detection_method: str
    contributing_factors: Dict[str, float]
    peak_idx: Optional[int] = None
    peak_temp: Optional[float] = None


class FuzzyMembershipFunctions:
    """
    Membership functions for fuzzy logic operations.

    All functions return a value between 0.0 and 1.0 indicating
    the degree of membership in a fuzzy set.
    """

    @staticmethod
    def trimf(x: float, params: Tuple[float, float, float]) -> float:
        """Triangular membership function."""
        a, b, c = params
        if x <= a or x >= c:
            return 0.0
        elif x == b:
            return 1.0
        elif a < x < b:
            return (x - a) / (b - a)
        else:  # b < x < c
            return (c - x) / (c - b)

    @staticmethod
    def trapmf(x: float, params: Tuple[float, float, float, float]) -> float:
        """Trapezoidal membership function."""
        a, b, c, d = params
        if x <= a or x >= d:
            return 0.0
        elif b <= x <= c:
            return 1.0
        elif a < x < b:
            return (x - a) / (b - a)
        else:  # c < x < d
            return (d - x) / (d - c)

    @staticmethod
    def gaussmf(x: float, params: Tuple[float, float]) -> float:
        """Gaussian membership function."""
        center, sigma = params
        return np.exp(-((x - center) ** 2) / (2 * sigma ** 2))

    @staticmethod
    def smf(x: float, params: Tuple[float, float]) -> float:
        """S-shaped membership function."""
        a, b = params
        if x <= a:
            return 0.0
        elif x >= b:
            return 1.0
        else:
            return 2 * ((x - a) / (b - a)) ** 2 if x <= (a + b) / 2 else 1 - 2 * ((b - x) / (b - a)) ** 2

    @staticmethod
    def zmf(x: float, params: Tuple[float, float]) -> float:
        """Z-shaped membership function (inverse of S)."""
        return 1.0 - FuzzyMembershipFunctions.smf(x, params)


class FuzzyTemperatureClassifier:
    """Classifies temperature values into fuzzy sets."""

    def __init__(self, temp_min: float = 15.0, temp_max: float = 250.0):
        """
        Initialize temperature classifier with adaptive ranges.

        Args:
            temp_min: Minimum expected temperature
            temp_max: Maximum expected temperature
        """
        self.temp_min = temp_min
        self.temp_max = temp_max
        self.mf = FuzzyMembershipFunctions()

        # Define temperature membership functions (adaptive)
        self.cold = (temp_min, temp_min, 25)
        self.cool = (18, 30, 45)
        self.warm = (35, 50, 70)
        self.hot = (60, 90, 140)
        self.very_hot = (120, 180, temp_max)

    def classify(self, temp: float) -> Dict[str, float]:
        """Return membership degrees for all temperature classes."""
        return {
            'cold': self.mf.trimf(temp, self.cold),
            'cool': self.mf.trimf(temp, self.cool),
            'warm': self.mf.trimf(temp, self.warm),
            'hot': self.mf.trimf(temp, self.hot),
            'very_hot': self.mf.trimf(temp, self.very_hot)
        }


class FuzzyGradientClassifier:
    """Classifies temperature gradients into fuzzy sets."""

    def __init__(self, sample_period_s: float = 5.0):
        """
        Initialize gradient classifier.

        Args:
            sample_period_s: Time between samples in seconds
        """
        self.sample_period = sample_period_s
        self.mf = FuzzyMembershipFunctions()

        # Gradient membership functions (°C per minute)
        self.rapid_cooling = (-20, -10, -5)
        self.cooling = (-8, -3, -0.5)
        self.stable = (-0.5, 0, 0.5)
        self.warming = (0.5, 2, 6)
        self.heating = (4, 8, 15)
        self.rapid_heating = (12, 20, 40)

    def classify(self, gradient: float) -> Dict[str, float]:
        """
        Classify temperature gradient (°C/sample).

        Args:
            gradient: Temperature change per sample (°C)

        Returns:
            Membership degrees for gradient classes
        """
        # Convert to °C/minute
        gradient_per_min = (gradient / self.sample_period) * 60

        return {
            'rapid_cooling': self.mf.trimf(gradient_per_min, self.rapid_cooling),
            'cooling': self.mf.trimf(gradient_per_min, self.cooling),
            'stable': self.mf.trimf(gradient_per_min, self.stable),
            'warming': self.mf.trimf(gradient_per_min, self.warming),
            'heating': self.mf.trimf(gradient_per_min, self.heating),
            'rapid_heating': self.mf.trimf(gradient_per_min, self.rapid_heating)
        }


class FuzzyStabilityClassifier:
    """Classifies temperature stability over a window."""

    def __init__(self):
        self.mf = FuzzyMembershipFunctions()

        # Stability measured as standard deviation (°C)
        self.very_stable = (0, 0, 0.5)
        self.stable = (0.3, 1.0, 2.0)
        self.fluctuating = (1.5, 3.0, 5.0)
        self.volatile = (4.0, 8.0, 20.0)

    def classify(self, std_dev: float) -> Dict[str, float]:
        """Classify temperature stability based on std deviation."""
        return {
            'very_stable': self.mf.trimf(std_dev, self.very_stable),
            'stable': self.mf.trimf(std_dev, self.stable),
            'fluctuating': self.mf.trimf(std_dev, self.fluctuating),
            'volatile': self.mf.trimf(std_dev, self.volatile)
        }


class FuzzyAmbientClassifier:
    """Classifies ambient temperature into fuzzy sets."""

    def __init__(self):
        self.mf = FuzzyMembershipFunctions()

        # Ambient temperature zones
        self.room_temp = (15, 20, 40)
        self.warm_ambient = (35, 55, 80)
        self.oven_temp = (70, 120, 200)
        self.peak_oven = (160, 220, 280)

    def classify(self, ambient_temp: float) -> Dict[str, float]:
        """Classify ambient temperature."""
        return {
            'room': self.mf.trimf(ambient_temp, self.room_temp),
            'warm': self.mf.trimf(ambient_temp, self.warm_ambient),
            'oven': self.mf.trimf(ambient_temp, self.oven_temp),
            'peak_oven': self.mf.trimf(ambient_temp, self.peak_oven)
        }


class FuzzyInferenceEngine:
    """
    Fuzzy inference engine that evaluates rules and combines evidence.
    """

    @staticmethod
    def fuzzy_and(*memberships: float) -> float:
        """Fuzzy AND operation (minimum)."""
        return min(memberships)

    @staticmethod
    def fuzzy_or(*memberships: float) -> float:
        """Fuzzy OR operation (maximum)."""
        return max(memberships)

    @staticmethod
    def fuzzy_not(membership: float) -> float:
        """Fuzzy NOT operation (complement)."""
        return 1.0 - membership

    def evaluate_start_rules(self,
                            temp_class: Dict[str, float],
                            grad_class: Dict[str, float],
                            ambient_class: Dict[str, float],
                            stability_class: Dict[str, float],
                            has_state_change: bool) -> Tuple[float, Dict[str, float]]:
        """
        Evaluate fuzzy rules for detecting bake start.

        Returns:
            Tuple of (confidence, contributing_factors)
        """
        factors = {}

        # Rule 1: Cold temp + rapid heating + oven ambient = HIGH confidence
        rule1 = self.fuzzy_and(
            temp_class.get('cold', 0),
            grad_class.get('rapid_heating', 0),
            ambient_class.get('oven', 0)
        )
        factors['cold_rapid_oven'] = rule1 * 0.95

        # Rule 2: Cool/warm + heating + oven = HIGH confidence
        rule2 = self.fuzzy_and(
            self.fuzzy_or(temp_class.get('cool', 0), temp_class.get('warm', 0)),
            grad_class.get('heating', 0),
            ambient_class.get('oven', 0)
        )
        factors['warm_heating_oven'] = rule2 * 0.90

        # Rule 3: Warm + rapid heating = MEDIUM-HIGH confidence
        rule3 = self.fuzzy_and(
            temp_class.get('warm', 0),
            grad_class.get('rapid_heating', 0)
        )
        factors['warm_rapid'] = rule3 * 0.85

        # Rule 4: Cool + heating + volatile = MEDIUM confidence (insertion transient)
        rule4 = self.fuzzy_and(
            temp_class.get('cool', 0),
            self.fuzzy_or(grad_class.get('heating', 0), grad_class.get('warming', 0)),
            stability_class.get('volatile', 0)
        )
        factors['cool_warming_volatile'] = rule4 * 0.75

        # Rule 5: State change from not_inserted + warm ambient = HIGH confidence
        if has_state_change:
            rule5 = self.fuzzy_or(
                ambient_class.get('warm', 0),
                ambient_class.get('oven', 0)
            )
            factors['state_change_ambient'] = rule5 * 0.88

        # Rule 6: Sustained heating from low temp = MEDIUM confidence
        rule6 = self.fuzzy_and(
            temp_class.get('cool', 0),
            grad_class.get('heating', 0)
        )
        factors['sustained_heating'] = rule6 * 0.70

        # Rule 7: Ambient transition to oven with any heating = HIGH confidence
        rule7 = self.fuzzy_and(
            ambient_class.get('oven', 0),
            self.fuzzy_or(
                grad_class.get('heating', 0),
                grad_class.get('rapid_heating', 0),
                grad_class.get('warming', 0)
            )
        )
        factors['ambient_oven_transition'] = rule7 * 0.92

        # Rule 8: High oven ambient alone (for pre-inserted probe with slow core heating)
        # Handles case where probe is in bread, bread is in oven,
        # ambient is high but core heats slowly due to thermal insulation
        rule8 = self.fuzzy_and(
            ambient_class.get('oven', 0),
            self.fuzzy_or(
                temp_class.get('cool', 0),
                temp_class.get('warm', 0)
            )
        )
        factors['oven_ambient_slow_core'] = rule8 * 0.68

        # Combine rules using fuzzy OR (max)
        confidence = self.fuzzy_or(*factors.values())

        return confidence, factors

    def evaluate_end_rules(self,
                          temp_class: Dict[str, float],
                          grad_class: Dict[str, float],
                          ambient_class: Dict[str, float],
                          stability_class: Dict[str, float],
                          temp_drop_from_peak: float,
                          time_at_low_temp: int) -> Tuple[float, Dict[str, float]]:
        """
        Evaluate fuzzy rules for detecting bake end.

        Args:
            temp_drop_from_peak: Degrees dropped from peak temperature
            time_at_low_temp: Number of samples at low temperature

        Returns:
            Tuple of (confidence, contributing_factors)
        """
        factors = {}

        # Rule 1: Rapid cooling = VERY HIGH confidence (probe removal)
        rule1 = grad_class.get('rapid_cooling', 0)
        factors['rapid_cooling'] = rule1 * 0.98

        # Rule 2: Cold + stable + time at low = HIGH confidence
        if time_at_low_temp > 20:  # >100 seconds at room temp
            rule2 = self.fuzzy_and(
                temp_class.get('cold', 0),
                self.fuzzy_or(
                    stability_class.get('stable', 0),
                    stability_class.get('very_stable', 0)
                )
            )
            factors['cold_stable_time'] = rule2 * 0.95

        # Rule 3: Large temperature drop from peak = HIGH confidence
        if temp_drop_from_peak > 40:
            drop_factor = min(1.0, temp_drop_from_peak / 60)
            factors['large_temp_drop'] = drop_factor * 0.93
        elif temp_drop_from_peak > 20:
            drop_factor = (temp_drop_from_peak - 20) / 40
            factors['medium_temp_drop'] = drop_factor * 0.75

        # Rule 4: Cooling + room ambient = MEDIUM-HIGH confidence
        rule4 = self.fuzzy_and(
            grad_class.get('cooling', 0),
            ambient_class.get('room', 0)
        )
        factors['cooling_room_ambient'] = rule4 * 0.85

        # Rule 5: Cool temp + cooling + ambient cooling = MEDIUM confidence
        rule5 = self.fuzzy_and(
            temp_class.get('cool', 0),
            grad_class.get('cooling', 0),
            self.fuzzy_or(ambient_class.get('room', 0), ambient_class.get('warm', 0))
        )
        factors['cool_cooling'] = rule5 * 0.72

        # Rule 6: Extended stable period at room temp = HIGH confidence
        if time_at_low_temp > 60:  # >5 minutes
            rule6 = self.fuzzy_and(
                temp_class.get('cold', 0),
                stability_class.get('very_stable', 0)
            )
            factors['extended_room_temp'] = rule6 * 0.90

        # Combine rules
        confidence = self.fuzzy_or(*factors.values())

        return confidence, factors


class FuzzyCurveDetector:
    """
    Main fuzzy logic detector for baking curves.
    """

    def __init__(self, sample_period_ms: int = 5000):
        """
        Initialize fuzzy curve detector.

        Args:
            sample_period_ms: Sample period in milliseconds
        """
        self.sample_period_s = sample_period_ms / 1000.0
        self.inference_engine = FuzzyInferenceEngine()

    def detect_curves(self, df: pd.DataFrame,
                     min_duration: int = 60,
                     min_peak_temp: float = 80.0,
                     confidence_threshold: float = 0.65) -> List[FuzzyDetectionResult]:
        """
        Detect all baking curves in the dataset using fuzzy logic.

        Args:
            df: DataFrame with temperature data
            min_duration: Minimum curve duration in samples
            min_peak_temp: Minimum peak temperature for valid curve
            confidence_threshold: Minimum confidence to accept detection

        Returns:
            List of detected curves with confidence scores
        """
        # Determine which column to use for core temperature
        core_col = 'CoreTemperature' if 'CoreTemperature' in df.columns else 'VirtualCoreTemperature'
        if core_col not in df.columns:
            # Fallback to T1
            core_col = 'T1'

        # Determine ambient column
        ambient_col = None
        if 'VirtualAmbientTemperature' in df.columns:
            ambient_col = 'VirtualAmbientTemperature'
        elif 'AmbientTemperature' in df.columns:
            ambient_col = 'AmbientTemperature'
        elif 'T8' in df.columns:
            ambient_col = 'T8'

        # Calculate adaptive parameters from data
        temp_min = df[core_col].min()
        temp_max = df[core_col].max()

        # Initialize classifiers with adaptive ranges
        temp_classifier = FuzzyTemperatureClassifier(temp_min, temp_max)
        grad_classifier = FuzzyGradientClassifier(self.sample_period_s)
        stability_classifier = FuzzyStabilityClassifier()
        ambient_classifier = FuzzyAmbientClassifier()

        # Calculate features for entire dataset
        df_features = self._calculate_features(df, core_col, ambient_col)

        # Find curve boundaries
        curves = []
        i = 0

        while i < len(df_features):
            # Find curve start
            start_result = self._find_start_fuzzy(
                df_features, i, temp_classifier, grad_classifier,
                ambient_classifier, stability_classifier, confidence_threshold
            )

            if start_result is None:
                break

            start_idx, start_conf, start_factors = start_result

            # Find curve peak
            peak_idx, peak_temp = self._find_peak(df_features, start_idx, core_col)

            # Find curve end
            end_result = self._find_end_fuzzy(
                df_features, start_idx, peak_idx, peak_temp, temp_classifier,
                grad_classifier, ambient_classifier, stability_classifier,
                confidence_threshold, core_col
            )

            if end_result is None:
                # No clear end found, use end of data
                end_idx = len(df_features) - 1
                end_conf = 0.5
                end_factors = {'default_end': 0.5}
            else:
                end_idx, end_conf, end_factors = end_result

            # Validate curve
            duration = end_idx - start_idx + 1
            if duration >= min_duration and peak_temp >= min_peak_temp:
                result = FuzzyDetectionResult(
                    start_idx=start_idx,
                    end_idx=end_idx,
                    start_confidence=start_conf,
                    end_confidence=end_conf,
                    detection_method='fuzzy_multimodal',
                    contributing_factors={
                        'start': start_factors,
                        'end': end_factors
                    },
                    peak_idx=peak_idx,
                    peak_temp=peak_temp
                )
                curves.append(result)

            # Move past this curve
            i = end_idx + 1

        return curves

    def _calculate_features(self, df: pd.DataFrame, core_col: str,
                           ambient_col: Optional[str]) -> pd.DataFrame:
        """Calculate features for fuzzy classification."""
        df_features = df.copy()

        # Temperature gradient (per sample)
        df_features['temp_gradient'] = df[core_col].diff().fillna(0)

        # Smoothed temperature for stability
        df_features['temp_smooth'] = df[core_col].rolling(window=5, center=True).mean().fillna(df[core_col])

        # Temperature stability (rolling std dev)
        df_features['temp_stability'] = df[core_col].rolling(window=10, center=True).std().fillna(0)

        # Ambient temperature features
        if ambient_col:
            df_features['ambient_temp'] = df[ambient_col]
            df_features['ambient_gradient'] = df[ambient_col].diff().fillna(0)
        else:
            df_features['ambient_temp'] = df[core_col] * 1.5  # Rough estimate
            df_features['ambient_gradient'] = 0

        # Acceleration (second derivative)
        df_features['temp_acceleration'] = df_features['temp_gradient'].diff().fillna(0)

        return df_features

    def _find_start_fuzzy(self, df: pd.DataFrame, start_search_idx: int,
                         temp_classifier: FuzzyTemperatureClassifier,
                         grad_classifier: FuzzyGradientClassifier,
                         ambient_classifier: FuzzyAmbientClassifier,
                         stability_classifier: FuzzyStabilityClassifier,
                         threshold: float) -> Optional[Tuple[int, float, Dict]]:
        """Find curve start using fuzzy logic."""
        best_idx = None
        best_confidence = 0.0
        best_factors = {}

        # Scan forward looking for start signal
        for i in range(start_search_idx, len(df) - 1):
            temp = df.iloc[i]['temp_smooth']
            gradient = df.iloc[i]['temp_gradient']
            stability = df.iloc[i]['temp_stability']
            ambient = df.iloc[i]['ambient_temp']

            # Check for state change
            has_state_change = False
            if 'PredictionState' in df.columns and i > 0:
                prev_state = df.iloc[i-1]['PredictionState']
                curr_state = df.iloc[i]['PredictionState']
                has_state_change = (prev_state == 'Probe Not Inserted' and
                                   curr_state != 'Probe Not Inserted')

            # Classify all features
            temp_class = temp_classifier.classify(temp)
            grad_class = grad_classifier.classify(gradient)
            ambient_class = ambient_classifier.classify(ambient)
            stability_class = stability_classifier.classify(stability)

            # Evaluate fuzzy rules
            confidence, factors = self.inference_engine.evaluate_start_rules(
                temp_class, grad_class, ambient_class, stability_class, has_state_change
            )

            # Keep track of best candidate
            if confidence > best_confidence:
                best_confidence = confidence
                best_idx = i
                best_factors = factors

            # If we found a high-confidence start, commit to it
            if confidence >= 0.85:
                return (i, confidence, factors)

        # Return best candidate if above threshold
        if best_confidence >= threshold:
            return (best_idx, best_confidence, best_factors)

        return None

    def _find_peak(self, df: pd.DataFrame, start_idx: int,
                   core_col: str) -> Tuple[int, float]:
        """Find temperature peak after start."""
        peak_idx = start_idx
        peak_temp = df.iloc[start_idx]['temp_smooth']

        # Stop search if we hit room temperature plateau
        room_temp_count = 0

        for i in range(start_idx + 1, len(df)):
            current_temp = df.iloc[i]['temp_smooth']

            if current_temp > peak_temp:
                peak_temp = current_temp
                peak_idx = i
                room_temp_count = 0

            # Stop if temperature drops to room temp for extended period
            if peak_temp > 70 and current_temp < 35:
                room_temp_count += 1
                if room_temp_count >= 20:
                    break
            else:
                room_temp_count = 0

        return peak_idx, peak_temp

    def _find_end_fuzzy(self, df: pd.DataFrame, start_idx: int, peak_idx: int,
                       peak_temp: float, temp_classifier: FuzzyTemperatureClassifier,
                       grad_classifier: FuzzyGradientClassifier,
                       ambient_classifier: FuzzyAmbientClassifier,
                       stability_classifier: FuzzyStabilityClassifier,
                       threshold: float, core_col: str) -> Optional[Tuple[int, float, Dict]]:
        """Find curve end using fuzzy logic."""
        # Start searching after reaching significant temperature
        search_start = start_idx
        for i in range(start_idx, peak_idx):
            if df.iloc[i]['temp_smooth'] > 70:
                search_start = i
                break

        best_idx = None
        best_confidence = 0.0
        best_factors = {}
        time_at_low = 0

        for i in range(search_start + 1, len(df)):
            temp = df.iloc[i]['temp_smooth']
            gradient = df.iloc[i]['temp_gradient']
            stability = df.iloc[i]['temp_stability']
            ambient = df.iloc[i]['ambient_temp']
            temp_drop = peak_temp - temp

            # Track time at low temperature
            if temp < 35:
                time_at_low += 1
            else:
                time_at_low = 0

            # Classify features
            temp_class = temp_classifier.classify(temp)
            grad_class = grad_classifier.classify(gradient)
            ambient_class = ambient_classifier.classify(ambient)
            stability_class = stability_classifier.classify(stability)

            # Evaluate end rules
            confidence, factors = self.inference_engine.evaluate_end_rules(
                temp_class, grad_class, ambient_class, stability_class,
                temp_drop, time_at_low
            )

            # Update best candidate
            if confidence > best_confidence:
                best_confidence = confidence
                best_idx = i
                best_factors = factors

            # Commit to very high confidence detections
            if confidence >= 0.90:
                return (i, confidence, factors)

        # Return best candidate if above threshold
        if best_confidence >= threshold:
            return (best_idx, best_confidence, best_factors)

        return None


def detect_curves_fuzzy(df: pd.DataFrame, sample_period_ms: int = 5000,
                        min_duration: int = 60, min_peak_temp: float = 80.0,
                        confidence_threshold: float = 0.65) -> List[FuzzyDetectionResult]:
    """
    Convenience function for fuzzy curve detection.

    Args:
        df: DataFrame with temperature data
        sample_period_ms: Sample period in milliseconds
        min_duration: Minimum curve duration in samples
        min_peak_temp: Minimum peak temperature
        confidence_threshold: Minimum confidence for detection

    Returns:
        List of detected curves with confidence scores
    """
    detector = FuzzyCurveDetector(sample_period_ms)
    return detector.detect_curves(df, min_duration, min_peak_temp, confidence_threshold)
