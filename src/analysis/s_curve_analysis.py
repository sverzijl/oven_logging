"""S-Curve analysis for bread baking optimization."""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from config.constants import S_CURVE_ZONES, S_CURVE_BENCHMARKS, BAKEOUT_TARGETS, PRODUCT_MOISTURE
from src.data.column_helpers import get_core_temperature_column


@dataclass
class SCurveLandmark:
    """Represents a critical point on the S-curve."""
    name: str
    temperature: float
    time_minutes: float
    time_percentage: float
    target_percentage_range: Tuple[float, float]
    is_within_target: bool


@dataclass
class BakeOutAnalysis:
    """Analysis of the bake-out zone characteristics."""
    start_time_minutes: float
    duration_minutes: float
    percentage_of_bake: float
    moisture_loss_rate: float
    final_moisture_estimate: float
    quality_assessment: str
    recommendations: List[str]


class SCurveAnalyzer:
    """Analyze S-curve characteristics for bread quality optimization."""
    
    def __init__(self, data: pd.DataFrame, metadata: Dict, loader=None,
                 product_type: str = 'white_pan'):
        self.data = data
        self.metadata = metadata
        self.sample_period = metadata.get('sample_period_s', 5.0)
        self.total_bake_time = len(data) * self.sample_period / 60.0
        self.loader = loader
        # Default 'white_pan' preserves existing behaviour for callers (tabs/)
        # that do not yet pass a product type (Wave B wires the sidebar
        # selector). Per-call product_type arguments override this default.
        self.product_type = product_type
        
    def identify_landmarks(self) -> Dict[str, SCurveLandmark]:
        """Identify critical landmarks on the S-curve."""
        landmarks = {}
        # Resolve the core column via the shared helper (CoreTemperature →
        # CoreAverage) like the rest of the class, instead of hardcoding the
        # standardized name (#23).
        core_temp = self.data[get_core_temperature_column(self.data)]
        
        # Yeast Kill (56°C)
        yeast_kill_idx = self._find_temperature_crossing(core_temp, 56)
        if yeast_kill_idx is not None:
            time_min = self.data.loc[yeast_kill_idx, 'TimeMinutes']
            time_pct = (time_min / self.total_bake_time) * 100
            target_range = S_CURVE_BENCHMARKS['YEAST_KILL']['target_percentage']
            
            landmarks['yeast_kill'] = SCurveLandmark(
                name="Yeast Kill",
                temperature=56,
                time_minutes=time_min,
                time_percentage=time_pct,
                target_percentage_range=target_range,
                is_within_target=target_range[0] <= time_pct <= target_range[1]
            )
        
        # Starch Gelatinization Complete (82°C)
        starch_complete_idx = self._find_temperature_crossing(core_temp, 82)
        if starch_complete_idx is not None:
            time_min = self.data.loc[starch_complete_idx, 'TimeMinutes']
            time_pct = (time_min / self.total_bake_time) * 100
            target_range = S_CURVE_BENCHMARKS['STARCH_COMPLETE']['target_percentage']
            
            landmarks['starch_complete'] = SCurveLandmark(
                name="Starch Gelatinization Complete",
                temperature=82,
                time_minutes=time_min,
                time_percentage=time_pct,
                target_percentage_range=target_range,
                is_within_target=target_range[0] <= time_pct <= target_range[1]
            )
        
        # Arrival Temperature (93°C)
        arrival_idx = self._find_temperature_crossing(core_temp, 93)
        if arrival_idx is not None:
            time_min = self.data.loc[arrival_idx, 'TimeMinutes']
            time_pct = (time_min / self.total_bake_time) * 100
            target_range = S_CURVE_BENCHMARKS['ARRIVAL_TEMP']['target_percentage']
            
            landmarks['arrival_temperature'] = SCurveLandmark(
                name="Arrival Temperature",
                temperature=93,
                time_minutes=time_min,
                time_percentage=time_pct,
                target_percentage_range=target_range,
                is_within_target=target_range[0] <= time_pct <= target_range[1]
            )
        
        return landmarks
    
    def analyze_zones(self) -> Dict[str, Dict]:
        """Analyze the three major S-curve zones."""
        zones = {}
        core_col = get_core_temperature_column(self.data)
        core_temp = self.data[core_col]
        
        # Oven Spring Zone (up to 56°C)
        oven_spring = self.data[core_temp < 56]
        if not oven_spring.empty:
            zones['oven_spring'] = {
                'duration_minutes': len(oven_spring) * self.sample_period / 60,
                'percentage_of_bake': (len(oven_spring) / len(self.data)) * 100,
                'max_temp_reached': oven_spring[core_col].max(),
                'expansion_rate': self._calculate_expansion_rate(oven_spring)
            }
        
        # Critical Change Zone (56-93°C)
        in_band = (core_temp >= 56) & (core_temp < 93)
        critical = self.data[in_band]
        if not critical.empty:
            zones['critical_change'] = {
                'duration_minutes': len(critical) * self.sample_period / 60,
                'percentage_of_bake': (len(critical) / len(self.data)) * 100,
                'max_temp_reached': critical[core_col].max(),
                # Compute the heating rate over the FIRST contiguous in-band run
                # rather than a raw boolean-mask diff(): on non-monotonic bakes
                # the masked subset is non-adjacent in the original index, so a
                # naive .diff() bridges the gaps and injects spurious jumps (#10).
                'avg_heating_rate': self._first_run_heating_rate(in_band, core_temp),
                'transformations': self._identify_transformations(critical)
            }
        
        # Bake-Out Zone (93°C and above)
        bakeout = self.data[core_temp >= 93]
        if not bakeout.empty:
            zones['bake_out'] = {
                'duration_minutes': len(bakeout) * self.sample_period / 60,
                'percentage_of_bake': (len(bakeout) / len(self.data)) * 100,
                'max_temp_reached': bakeout[core_col].max(),
                'moisture_loss_estimate': self._estimate_moisture_loss(bakeout)
            }
        
        return zones
    
    def analyze_bake_out(self, product_type: Optional[str] = None) -> BakeOutAnalysis:
        """Perform detailed bake-out analysis with improved moisture model.

        Args:
            product_type: Product key into BAKEOUT_TARGETS / PRODUCT_MOISTURE.
                Defaults to the analyzer's ``product_type`` (itself 'white_pan'
                unless set), preserving prior behaviour (#8).
        """
        if product_type is None:
            product_type = self.product_type
        core_col = get_core_temperature_column(self.data)
        core_temp = self.data[core_col]
        bakeout_data = self.data[core_temp >= 93]
        
        # Get product-specific parameters
        moisture_params = PRODUCT_MOISTURE.get(product_type, PRODUCT_MOISTURE['white_pan'])
        
        if bakeout_data.empty:
            return BakeOutAnalysis(
                start_time_minutes=self.total_bake_time,
                duration_minutes=0,
                percentage_of_bake=0,
                moisture_loss_rate=0,
                final_moisture_estimate=moisture_params['initial_moisture'],
                quality_assessment="Severely Underbaked",
                recommendations=["Increase bake time significantly", "Check oven temperature calibration"]
            )
        
        start_time = bakeout_data.iloc[0]['TimeMinutes']
        # Drive duration off the real per-sample TimeMinutes (relative to the
        # bake-out start) so single-sample bake-outs still register a non-zero
        # elapsed time instead of collapsing to 0 (#6).
        duration = self._bakeout_duration_minutes(bakeout_data)
        percentage = (len(bakeout_data) / len(self.data)) * 100

        # Get product-specific targets
        target_range = BAKEOUT_TARGETS.get(product_type, BAKEOUT_TARGETS['white_pan'])

        # Calculate moisture loss. The endpoint is anchored to where bake-out%
        # sits relative to its target window so the moisture verdict and the
        # bake-out% verdict stay internally consistent (#5); the exponential
        # decay shape governs only the relative trajectory / loss-rate report.
        final_moisture, avg_loss_rate = self._calculate_moisture_loss_exponential(
            bakeout_data, duration, moisture_params, percentage, target_range
        )

        # Quality assessment
        quality, recommendations = self._assess_bakeout_quality(
            percentage, target_range, final_moisture, moisture_params['target_final']
        )
        
        return BakeOutAnalysis(
            start_time_minutes=start_time,
            duration_minutes=duration,
            percentage_of_bake=percentage,
            moisture_loss_rate=avg_loss_rate,
            final_moisture_estimate=final_moisture,
            quality_assessment=quality,
            recommendations=recommendations
        )
    
    def diagnose_quality_issues(self, product_type: Optional[str] = None) -> List[Dict]:
        """Diagnose quality issues based on S-curve analysis.

        Args:
            product_type: Product key used for product-aware bake-out thresholds.
                Defaults to the analyzer's ``product_type`` (#8).
        """
        if product_type is None:
            product_type = self.product_type
        issues = []
        landmarks = self.identify_landmarks()
        zones = self.analyze_zones()
        bakeout = self.analyze_bake_out(product_type)
        
        # Check yeast kill timing
        if 'yeast_kill' in landmarks:
            yk = landmarks['yeast_kill']
            if yk.time_percentage < 45:
                issues.append({
                    'issue': 'Early Yeast Kill',
                    'severity': 'High',
                    'impact': 'Poor oven spring, low loaf volume',
                    'cause': f'Yeast kill at {yk.time_percentage:.1f}% (target: 45-55%)',
                    'recommendation': 'Reduce initial oven temperature or slow heating rate'
                })
            elif yk.time_percentage > 55:
                issues.append({
                    'issue': 'Late Yeast Kill',
                    'severity': 'Medium',
                    'impact': 'Risk of blow-outs, white smiles on buns',
                    'cause': f'Yeast kill at {yk.time_percentage:.1f}% (target: 45-55%)',
                    'recommendation': 'Increase initial oven temperature'
                })
        
        # Check bake-out percentage against the product-specific target window
        # (#7 — was hardcoded 10%/20% literals that ignored product type).
        bo_min, bo_max = BAKEOUT_TARGETS.get(product_type, BAKEOUT_TARGETS['white_pan'])
        if bakeout.percentage_of_bake > bo_max:
            issues.append({
                'issue': 'Excessive Bake-Out',
                'severity': 'High',
                'impact': 'Dry, crumbly texture, rapid staling',
                'cause': f'Bake-out at {bakeout.percentage_of_bake:.1f}% (>{bo_max}% for {product_type})',
                'recommendation': 'Reduce bake time or lower temperature in final zones'
            })
        elif bakeout.percentage_of_bake < bo_min:
            issues.append({
                'issue': 'Insufficient Bake-Out',
                'severity': 'High',
                'impact': 'Gummy texture, poor shelf life, mold risk',
                'cause': f'Bake-out at {bakeout.percentage_of_bake:.1f}% (<{bo_min}% for {product_type})',
                'recommendation': 'Increase bake time or raise final zone temperature'
            })
        
        # Check starch gelatinization
        if 'starch_complete' in landmarks:
            sc = landmarks['starch_complete']
            if not sc.is_within_target:
                issues.append({
                    'issue': 'Suboptimal Starch Gelatinization',
                    'severity': 'Medium',
                    'impact': 'Weak crumb structure, poor texture',
                    'cause': f'Completion at {sc.time_percentage:.1f}% (target: 55-65%)',
                    'recommendation': 'Adjust middle zone temperatures for optimal timing'
                })
        
        return issues
    
    def generate_optimization_report(self, product_type: Optional[str] = None) -> Dict:
        """Generate comprehensive optimization report.

        Args:
            product_type: Product key threaded into the bake-out analysis and
                quality diagnosis. Defaults to the analyzer's ``product_type`` (#8).
        """
        if product_type is None:
            product_type = self.product_type
        landmarks = self.identify_landmarks()
        zones = self.analyze_zones()
        bakeout = self.analyze_bake_out(product_type)
        issues = self.diagnose_quality_issues(product_type)
        
        # Calculate overall S-curve quality score
        score = self._calculate_s_curve_score(landmarks, zones, bakeout)
        
        # Generate specific recommendations
        recommendations = self._generate_recommendations(landmarks, zones, bakeout, issues)
        
        return {
            'overall_score': score,
            'landmarks': landmarks,
            'zone_analysis': zones,
            'bakeout_analysis': bakeout,
            'quality_issues': issues,
            'recommendations': recommendations,
            'summary': self._generate_summary(score, issues)
        }
    
    def _find_temperature_crossing(self, temp_series: pd.Series, target: float) -> Optional[int]:
        """Find index where temperature first crosses target value."""
        crossings = temp_series >= target
        if crossings.any():
            return crossings.idxmax()
        return None
    
    def _first_run_heating_rate(self, in_band: pd.Series, core_temp: pd.Series) -> float:
        """Heating rate (°C/min) over the first contiguous in-band run.

        ``in_band`` is a boolean mask (aligned with ``core_temp``) marking the
        samples inside a temperature band. Computing a rate from the masked
        subset directly is unsafe on non-monotonic bakes because the selected
        rows are not adjacent in time. Instead we locate the first maximal run
        of consecutive True values (by positional order) and take the
        end-to-end slope across the real elapsed time of that run (#10).
        """
        mask = in_band.to_numpy()
        if not mask.any():
            return 0.0

        # Identify run boundaries on the positional (time-ordered) mask.
        idx = np.flatnonzero(mask)
        # Split where positional index is non-consecutive.
        breaks = np.flatnonzero(np.diff(idx) > 1)
        first_run_end = breaks[0] if breaks.size else len(idx) - 1
        start_pos = idx[0]
        end_pos = idx[first_run_end]

        if end_pos == start_pos:
            # Single in-band sample: rate is undefined → 0.
            return 0.0

        temps = core_temp.to_numpy()
        delta_temp = temps[end_pos] - temps[start_pos]
        n_steps = end_pos - start_pos
        elapsed_minutes = n_steps * self.sample_period / 60.0
        if elapsed_minutes <= 0:
            return 0.0
        return delta_temp / elapsed_minutes

    def _calculate_expansion_rate(self, oven_spring_data: pd.DataFrame) -> float:
        """Estimate expansion rate during oven spring."""
        core_col = get_core_temperature_column(oven_spring_data)
        # Simplified calculation based on temperature rise rate
        temp_rise = oven_spring_data[core_col].diff().mean()
        return temp_rise * 0.8  # Empirical factor
    
    def _identify_transformations(self, critical_data: pd.DataFrame) -> List[str]:
        """Identify biochemical transformations in critical zone."""
        transformations = []
        core_col = get_core_temperature_column(critical_data)
        temp_range = critical_data[core_col]
        
        if any((temp_range >= 56) & (temp_range <= 60)):
            transformations.append("Yeast inactivation")
        if any((temp_range >= 65) & (temp_range <= 82)):
            transformations.append("Starch gelatinization")
        if any((temp_range >= 71) & (temp_range <= 85)):
            transformations.append("Protein denaturation")
        
        return transformations
    
    def _bakeout_duration_minutes(self, bakeout_data: pd.DataFrame) -> float:
        """Elapsed bake-out duration (minutes) from the real per-sample times.

        Uses the actual ``TimeMinutes`` span of the bake-out window rather than
        ``len * sample_period``; for a single bake-out sample we fall back to one
        sample period so the duration never collapses to zero (#6).
        """
        if bakeout_data.empty:
            return 0.0
        if len(bakeout_data) == 1:
            # One sample at/above 93°C: credit one sample period of elapsed time.
            return self.sample_period / 60.0
        times = bakeout_data['TimeMinutes']
        return float(times.iloc[-1] - times.iloc[0])

    def _calculate_moisture_loss_exponential(self, bakeout_data: pd.DataFrame,
                                           duration: float,
                                           moisture_params: Dict,
                                           bakeout_percentage: float = None,
                                           target_range: Tuple[float, float] = None
                                           ) -> Tuple[float, float]:
        """
        Estimate final moisture from the bake-out profile.

        IMPORTANT CALIBRATION NOTE
        --------------------------
        ``k_factor`` (and the exponential crust-barrier shape below) are NOT
        physically calibrated — they have no backing from real lab
        bake-out%→final-moisture measurements. The raw exponential model is
        retained only as a *relative / directional* trajectory indicator and to
        derive an average loss rate; it must NOT be presented as a physically
        accurate moisture figure.

        To keep the moisture verdict INTERNALLY CONSISTENT with the bake-out%
        verdict (#5), the reported ``final_moisture`` is *anchored* to where the
        bake-out percentage sits relative to its product target window: a
        bake-out% at the low edge of the window maps to the wet edge of the
        product's ``target_final`` window, the high edge maps to the dry edge,
        with monotonic extrapolation outside. This guarantees that an in-window
        bake-out% yields an in-window moisture (never "underbaked + excess
        moisture" simultaneously). Calibrating against real bake-out%→moisture
        lab data is a future follow-up.

        Returns:
            Tuple of (final_moisture, average_loss_rate)
        """
        initial_moisture = moisture_params['initial_moisture']
        target_final = moisture_params.get('target_final')

        # --- Relative/directional exponential trajectory (uncalibrated) -------
        # Retained to compute a smooth average loss rate and as a directional
        # cue; its absolute endpoint is intentionally NOT used as the verdict.
        k_factor = moisture_params['k_factor']
        crust_factor = moisture_params['crust_factor']
        core_col = get_core_temperature_column(bakeout_data)
        avg_temp = bakeout_data[core_col].mean()
        temp_adjustment = 1 + (avg_temp - 93) * 0.02  # 2% per °C above 93°C (uncalibrated)
        k_adjusted = k_factor * temp_adjustment

        # --- Anchored endpoint (the reported moisture) ------------------------
        if (bakeout_percentage is not None and target_range is not None
                and target_final is not None):
            bo_min, bo_max = target_range
            tf_min, tf_max = target_final
            # Map bake-out% → moisture, inverted and monotonic:
            #   % == bo_min  → moisture == tf_max (wettest acceptable)
            #   % == bo_max  → moisture == tf_min (driest acceptable)
            if bo_max > bo_min:
                frac = (bakeout_percentage - bo_min) / (bo_max - bo_min)
            else:
                frac = 0.0
            final_moisture = tf_max - frac * (tf_max - tf_min)
            # Clamp to a physically sane band: never wetter than initial, never
            # below an absolute dryness floor.
            final_moisture = max(min(final_moisture, initial_moisture), 0.0)
        else:
            # Backward-compatible path (e.g. the legacy estimate helper) — use
            # the uncalibrated exponential endpoint.
            crust_development = 1 / (1 + np.exp(-0.3 * (duration - duration / 2)))
            effective_crust_factor = 1 - (1 - crust_factor) * crust_development
            moisture_lost = initial_moisture * (
                1 - np.exp(-k_adjusted * duration * effective_crust_factor))
            final_moisture = initial_moisture - moisture_lost

        total_loss = initial_moisture - final_moisture
        avg_loss_rate = total_loss / duration if duration > 0 else 0

        return final_moisture, avg_loss_rate

    def _estimate_moisture_loss(self, bakeout_data: pd.DataFrame) -> float:
        """Legacy method - kept for compatibility."""
        duration = self._bakeout_duration_minutes(bakeout_data)
        moisture_params = PRODUCT_MOISTURE['white_pan']  # Default
        final_moisture, _ = self._calculate_moisture_loss_exponential(
            bakeout_data, duration, moisture_params
        )
        return moisture_params['initial_moisture'] - final_moisture
    
    def _assess_bakeout_quality(self, percentage: float, target_range: Tuple[float, float], 
                               final_moisture: float, moisture_target: Tuple[float, float]) -> Tuple[str, List[str]]:
        """Assess bake-out quality and generate recommendations."""
        recs = []
        
        # Assess bake-out percentage.
        # #25: the prior wording presented a percentage-POINT delta on the
        # bake-out fraction as if it were a directly actionable "extend bake
        # time by X% of total bake" figure. A %-point of bake-out fraction is
        # not the same as a bake-time extension, so convert it into an
        # approximate added time-above-93°C in minutes (delta_pct/100 of the
        # total bake duration) and flag it as a directional estimate.
        if percentage < target_range[0]:
            quality = "Underbaked"
            delta_pct = target_range[0] - percentage
            added_minutes = (delta_pct / 100.0) * self.total_bake_time
            recs.append(f"Increase bake-out to {target_range[0]}% (currently {percentage:.1f}%)")
            recs.append(
                f"Approx. {added_minutes:.1f} more min above 93°C needed "
                f"(directional estimate, not lab-calibrated)"
            )
        elif percentage > target_range[1]:
            quality = "Overbaked"
            delta_pct = percentage - target_range[1]
            removed_minutes = (delta_pct / 100.0) * self.total_bake_time
            recs.append(f"Reduce bake-out to {target_range[1]}% (currently {percentage:.1f}%)")
            recs.append(
                f"Approx. {removed_minutes:.1f} fewer min above 93°C needed "
                f"(directional estimate, not lab-calibrated)"
            )
        else:
            quality = "Optimal"
        
        # Assess final moisture
        if final_moisture < moisture_target[0]:
            if quality == "Optimal":
                quality = "Dry"
            recs.append(f"Product too dry: {final_moisture:.1f}% moisture (target: {moisture_target[0]}-{moisture_target[1]}%)")
            recs.append("Consider reducing final zone temperature by 5-10°C")
        elif final_moisture > moisture_target[1]:
            if quality == "Optimal":
                quality = "High Moisture"
            recs.append(f"Excess moisture: {final_moisture:.1f}% (target: {moisture_target[0]}-{moisture_target[1]}%)")
            recs.append("Increase final zone temperature or extend bake time slightly")
        else:
            if quality == "Optimal":
                recs.append(f"Moisture content optimal: {final_moisture:.1f}% (target: {moisture_target[0]}-{moisture_target[1]}%)")
                recs.append("Maintain current settings")
        
        return quality, recs
    
    def _calculate_s_curve_score(self, landmarks: Dict, zones: Dict, 
                                bakeout: BakeOutAnalysis) -> float:
        """Calculate overall S-curve quality score (0-100)."""
        score = 100.0
        
        # Deduct for landmark deviations
        for landmark in landmarks.values():
            if not landmark.is_within_target:
                deviation = abs(landmark.time_percentage - 
                              np.mean(landmark.target_percentage_range))
                score -= min(deviation * 2, 20)  # Max 20 points per landmark
        
        # Deduct for bake-out issues
        if bakeout.quality_assessment != "Optimal":
            score -= 15
        
        # Deduct for missing landmarks
        expected_landmarks = ['yeast_kill', 'starch_complete', 'arrival_temperature']
        missing = len([l for l in expected_landmarks if l not in landmarks])
        score -= missing * 10
        
        return max(0, score)
    
    def _generate_recommendations(self, landmarks: Dict, zones: Dict, 
                                 bakeout: BakeOutAnalysis, issues: List[Dict]) -> List[Dict]:
        """Generate prioritized recommendations."""
        recommendations = []
        
        # High priority issues
        high_priority = [i for i in issues if i['severity'] == 'High']
        for issue in high_priority:
            recommendations.append({
                'priority': 'High',
                'action': issue['recommendation'],
                'expected_result': f"Resolve: {issue['impact']}"
            })
        
        # Zone-specific optimizations
        if 'oven_spring' in zones and zones['oven_spring']['percentage_of_bake'] < 40:
            recommendations.append({
                'priority': 'Medium',
                'action': 'Extend oven spring phase by reducing initial heat',
                'expected_result': 'Improved loaf volume and crumb structure'
            })
        
        # Bake-out optimizations
        if bakeout.recommendations:
            for rec in bakeout.recommendations[:2]:  # Top 2 recommendations
                recommendations.append({
                    'priority': 'High' if 'significantly' in rec else 'Medium',
                    'action': rec,
                    'expected_result': 'Optimal moisture and texture'
                })
        
        return recommendations
    
    def _generate_summary(self, score: float, issues: List[Dict]) -> str:
        """Generate executive summary."""
        if score >= 90:
            quality = "Excellent"
        elif score >= 75:
            quality = "Good"
        elif score >= 60:
            quality = "Acceptable"
        else:
            quality = "Poor"
        
        high_issues = len([i for i in issues if i['severity'] == 'High'])
        
        summary = f"S-Curve Quality: {quality} (Score: {score:.1f}/100)\n"
        summary += f"Critical Issues: {high_issues}\n"
        
        if high_issues > 0:
            summary += "Immediate attention required for optimal bread quality."
        elif len(issues) > 0:
            summary += "Minor optimizations recommended for consistency."
        else:
            summary += "Baking profile well-optimized."
        
        return summary