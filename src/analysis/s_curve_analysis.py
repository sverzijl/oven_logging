"""S-Curve analysis for bread baking optimization."""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from config.constants import S_CURVE_ZONES, S_CURVE_BENCHMARKS, BAKEOUT_TARGETS, PRODUCT_MOISTURE


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
    
    def __init__(self, data: pd.DataFrame, metadata: Dict):
        self.data = data
        self.metadata = metadata
        self.sample_period = metadata.get('sample_period_s', 5.0)
        self.total_bake_time = len(data) * self.sample_period / 60.0
        
    def identify_landmarks(self) -> Dict[str, SCurveLandmark]:
        """Identify critical landmarks on the S-curve."""
        landmarks = {}
        # Use CoreTemperature if available, otherwise fall back to CoreAverage
        core_col = 'CoreTemperature' if 'CoreTemperature' in self.data.columns else 'CoreAverage'
        core_temp = self.data[core_col]
        
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
        # Use CoreTemperature if available, otherwise fall back to CoreAverage
        core_col = 'CoreTemperature' if 'CoreTemperature' in self.data.columns else 'CoreAverage'
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
        critical = self.data[(core_temp >= 56) & (core_temp < 93)]
        if not critical.empty:
            zones['critical_change'] = {
                'duration_minutes': len(critical) * self.sample_period / 60,
                'percentage_of_bake': (len(critical) / len(self.data)) * 100,
                'avg_heating_rate': critical[core_col].diff().mean() / (self.sample_period / 60),
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
    
    def analyze_bake_out(self, product_type: str = 'white_pan') -> BakeOutAnalysis:
        """Perform detailed bake-out analysis with improved moisture model."""
        # Use CoreTemperature if available, otherwise fall back to CoreAverage
        core_col = 'CoreTemperature' if 'CoreTemperature' in self.data.columns else 'CoreAverage'
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
        duration = len(bakeout_data) * self.sample_period / 60
        percentage = (len(bakeout_data) / len(self.data)) * 100
        
        # Calculate moisture loss using exponential model with temperature dependency
        final_moisture, avg_loss_rate = self._calculate_moisture_loss_exponential(
            bakeout_data, duration, moisture_params
        )
        
        # Get product-specific targets
        target_range = BAKEOUT_TARGETS.get(product_type, BAKEOUT_TARGETS['white_pan'])
        
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
    
    def diagnose_quality_issues(self) -> List[Dict]:
        """Diagnose quality issues based on S-curve analysis."""
        issues = []
        landmarks = self.identify_landmarks()
        zones = self.analyze_zones()
        bakeout = self.analyze_bake_out()
        
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
        
        # Check bake-out percentage
        if bakeout.percentage_of_bake > 20:
            issues.append({
                'issue': 'Excessive Bake-Out',
                'severity': 'High',
                'impact': 'Dry, crumbly texture, rapid staling',
                'cause': f'Bake-out at {bakeout.percentage_of_bake:.1f}% (>20%)',
                'recommendation': 'Reduce bake time or lower temperature in final zones'
            })
        elif bakeout.percentage_of_bake < 10:
            issues.append({
                'issue': 'Insufficient Bake-Out',
                'severity': 'High',
                'impact': 'Gummy texture, poor shelf life, mold risk',
                'cause': f'Bake-out at {bakeout.percentage_of_bake:.1f}% (<10%)',
                'recommendation': 'Increase bake time by 3-5% or raise final zone temperature'
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
    
    def generate_optimization_report(self) -> Dict:
        """Generate comprehensive optimization report."""
        landmarks = self.identify_landmarks()
        zones = self.analyze_zones()
        bakeout = self.analyze_bake_out()
        issues = self.diagnose_quality_issues()
        
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
    
    def _calculate_expansion_rate(self, oven_spring_data: pd.DataFrame) -> float:
        """Estimate expansion rate during oven spring."""
        # Use CoreTemperature if available, otherwise fall back to CoreAverage
        core_col = 'CoreTemperature' if 'CoreTemperature' in oven_spring_data.columns else 'CoreAverage'
        # Simplified calculation based on temperature rise rate
        temp_rise = oven_spring_data[core_col].diff().mean()
        return temp_rise * 0.8  # Empirical factor
    
    def _identify_transformations(self, critical_data: pd.DataFrame) -> List[str]:
        """Identify biochemical transformations in critical zone."""
        transformations = []
        # Use CoreTemperature if available, otherwise fall back to CoreAverage
        core_col = 'CoreTemperature' if 'CoreTemperature' in critical_data.columns else 'CoreAverage'
        temp_range = critical_data[core_col]
        
        if any((temp_range >= 56) & (temp_range <= 60)):
            transformations.append("Yeast inactivation")
        if any((temp_range >= 65) & (temp_range <= 82)):
            transformations.append("Starch gelatinization")
        if any((temp_range >= 71) & (temp_range <= 85)):
            transformations.append("Protein denaturation")
        
        return transformations
    
    def _calculate_moisture_loss_exponential(self, bakeout_data: pd.DataFrame, 
                                           duration: float, 
                                           moisture_params: Dict) -> Tuple[float, float]:
        """
        Calculate moisture loss using exponential decay model with crust effect.
        
        Returns:
            Tuple of (final_moisture, average_loss_rate)
        """
        initial_moisture = moisture_params['initial_moisture']
        k_factor = moisture_params['k_factor']
        crust_factor = moisture_params['crust_factor']
        
        # Temperature-adjusted k factor
        # Use CoreTemperature if available, otherwise fall back to CoreAverage
        core_col = 'CoreTemperature' if 'CoreTemperature' in bakeout_data.columns else 'CoreAverage'
        avg_temp = bakeout_data[core_col].mean()
        temp_adjustment = 1 + (avg_temp - 93) * 0.02  # 2% increase per degree above 93°C
        k_adjusted = k_factor * temp_adjustment
        
        # Time-varying crust barrier effect (crust forms progressively)
        time_points = np.linspace(0, duration, len(bakeout_data))
        moisture_values = []
        
        for i, t in enumerate(time_points):
            # Crust barrier increases over time (sigmoid function)
            crust_development = 1 / (1 + np.exp(-0.3 * (t - duration/2)))
            effective_crust_factor = 1 - (1 - crust_factor) * crust_development
            
            # Exponential decay with crust barrier
            moisture_lost = initial_moisture * (1 - np.exp(-k_adjusted * t * effective_crust_factor))
            current_moisture = initial_moisture - moisture_lost
            moisture_values.append(current_moisture)
        
        final_moisture = moisture_values[-1] if moisture_values else initial_moisture
        total_loss = initial_moisture - final_moisture
        avg_loss_rate = total_loss / duration if duration > 0 else 0
        
        return final_moisture, avg_loss_rate
    
    def _estimate_moisture_loss(self, bakeout_data: pd.DataFrame) -> float:
        """Legacy method - kept for compatibility."""
        duration = len(bakeout_data) * self.sample_period / 60
        moisture_params = PRODUCT_MOISTURE['white_pan']  # Default
        final_moisture, _ = self._calculate_moisture_loss_exponential(
            bakeout_data, duration, moisture_params
        )
        return moisture_params['initial_moisture'] - final_moisture
    
    def _assess_bakeout_quality(self, percentage: float, target_range: Tuple[float, float], 
                               final_moisture: float, moisture_target: Tuple[float, float]) -> Tuple[str, List[str]]:
        """Assess bake-out quality and generate recommendations."""
        recs = []
        
        # Assess bake-out percentage
        if percentage < target_range[0]:
            quality = "Underbaked"
            time_increase = target_range[0] - percentage
            recs.append(f"Increase bake-out to {target_range[0]}% (currently {percentage:.1f}%)")
            recs.append(f"Extend bake time by approximately {time_increase:.1f}% of total bake")
        elif percentage > target_range[1]:
            quality = "Overbaked"
            time_decrease = percentage - target_range[1]
            recs.append(f"Reduce bake-out to {target_range[1]}% (currently {percentage:.1f}%)")
            recs.append(f"Decrease bake time by approximately {time_decrease:.1f}% of total bake")
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