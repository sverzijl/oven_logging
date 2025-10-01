# Fuzzy Logic Curve Detection - User Guide

## Overview

This application now includes a state-of-the-art **fuzzy logic algorithm** for detecting the start and end points of baking curves. This advanced detection method provides:

- **Higher accuracy** through multi-signal integration
- **Confidence scoring** for each detection
- **Explainable decisions** showing which factors contributed
- **Adaptive thresholds** that self-tune to your data
- **Robust handling** of edge cases (pre-inserted probes, slow warmup, etc.)

## What is Fuzzy Logic?

Unlike traditional "hard" thresholds (e.g., "temperature > 40°C"), fuzzy logic uses **soft boundaries** where signals gradually transition between states. This mimics human reasoning and handles uncertainty better.

### Example: Temperature Classification

**Traditional approach:**
- Cold: < 30°C
- Warm: 30-60°C
- Hot: > 60°C

Problem: What if temperature is 29.9°C? It's classified as "cold" even though it's almost "warm".

**Fuzzy approach:**
- At 29°C: 90% cold, 10% warm
- At 30°C: 50% cold, 50% warm
- At 31°C: 10% cold, 90% warm

This gradual transition provides more nuanced decision-making.

## How It Works

### 1. Multi-Signal Analysis

The fuzzy detector evaluates **multiple temperature signals simultaneously**:

- **Core Temperature** (T1-T4): Primary signal for baking progress
- **Ambient Temperature** (T8): Indicates oven environment
- **Surface Temperature** (T7): Interface between product and oven
- **Temperature Gradient**: Rate of heating/cooling (°C/min)
- **Temperature Stability**: Variance over time windows
- **Probe State**: Hardware-reported insertion status

### 2. Fuzzy Membership Functions

Each signal is classified using membership functions:

#### Temperature Classification:
- `cold`: 15-25°C (room temperature)
- `cool`: 18-45°C (warming phase)
- `warm`: 35-70°C (early baking)
- `hot`: 60-140°C (active baking)
- `very_hot`: 120-250°C (peak/crust formation)

#### Gradient Classification (°C/min):
- `rapid_cooling`: -20 to -5°C/min (probe removal)
- `cooling`: -8 to -0.5°C/min (end of bake)
- `stable`: -0.5 to +0.5°C/min (holding)
- `warming`: +0.5 to +6°C/min (slow heating)
- `heating`: +4 to +15°C/min (active heating)
- `rapid_heating`: +12 to +40°C/min (oven entry)

#### Ambient Classification:
- `room`: 15-40°C
- `warm`: 35-80°C
- `oven`: 70-200°C
- `peak_oven`: 160-280°C

#### Stability Classification (std dev):
- `very_stable`: 0-0.5°C (steady state)
- `stable`: 0.3-2.0°C (minor fluctuations)
- `fluctuating`: 1.5-5.0°C (active changes)
- `volatile`: 4.0-20°C (rapid transitions)

### 3. Fuzzy Inference Rules

The system applies rules that combine multiple signals:

#### Start Detection Rules:

**Rule 1 (95% confidence):**
```
IF temp=cold AND gradient=rapid_heating AND ambient=oven
THEN start_detected (probe inserted into oven from cold)
```

**Rule 2 (90% confidence):**
```
IF (temp=cool OR temp=warm) AND gradient=heating AND ambient=oven
THEN start_detected (probe warming in oven)
```

**Rule 3 (88% confidence):**
```
IF state_change="not_inserted→inserted" AND ambient=warm/oven
THEN start_detected (hardware state change + ambient confirmation)
```

**Rule 4 (85% confidence):**
```
IF temp=warm AND gradient=rapid_heating
THEN start_detected (pre-warmed probe entering oven)
```

**Rule 5 (92% confidence):**
```
IF ambient=oven AND (gradient=heating OR gradient=rapid_heating OR gradient=warming)
THEN start_detected (ambient temperature indicates oven entry)
```

#### End Detection Rules:

**Rule 1 (98% confidence):**
```
IF gradient=rapid_cooling
THEN end_detected (probe removal signature)
```

**Rule 2 (95% confidence):**
```
IF temp=cold AND stability=stable AND time_at_room>100s
THEN end_detected (settled at room temperature)
```

**Rule 3 (93% confidence):**
```
IF temp_drop_from_peak>40°C
THEN end_detected (large temperature drop)
```

**Rule 4 (85% confidence):**
```
IF gradient=cooling AND ambient=room
THEN end_detected (cooling in room environment)
```

**Rule 5 (90% confidence):**
```
IF temp=cold AND stability=very_stable AND time_at_room>300s
THEN end_detected (extended room temperature plateau)
```

### 4. Confidence Aggregation

Multiple rules can fire simultaneously. The system combines them using **fuzzy OR** (maximum operator):

Example:
- Rule 1 fires at 0.85
- Rule 2 fires at 0.70
- Rule 3 fires at 0.92

**Final confidence = max(0.85, 0.70, 0.92) = 0.92**

This means the detection is driven primarily by Rule 3, with support from Rules 1 and 2.

## Configuration

Edit `config/constants.py` to adjust fuzzy detection settings:

```python
FUZZY_DETECTION_CONFIG = {
    "USE_FUZZY_DETECTION": True,      # Enable/disable fuzzy logic
    "CONFIDENCE_THRESHOLD": 0.65,      # Min confidence to accept detection (0.0-1.0)
    "MIN_CURVE_DURATION": 60,          # Min samples (5 min at 5s intervals)
    "MIN_PEAK_TEMP": 80.0,             # Min peak temperature (°C)
    "FALLBACK_TO_CLASSIC": True,       # Use classic method if fuzzy fails
    "LOG_CONFIDENCE": True,            # Print confidence scores to console
    "SHOW_CONFIDENCE_IN_UI": True      # Display scores in UI (future)
}
```

### Recommended Settings by Use Case:

**High Precision (research/quality control):**
```python
"CONFIDENCE_THRESHOLD": 0.75,  # Only accept high-confidence detections
"FALLBACK_TO_CLASSIC": False,  # No fallback, fuzzy only
```

**Balanced (production):**
```python
"CONFIDENCE_THRESHOLD": 0.65,  # Accept medium-high confidence
"FALLBACK_TO_CLASSIC": True,   # Fallback if fuzzy fails
```

**Maximum Coverage (exploration):**
```python
"CONFIDENCE_THRESHOLD": 0.55,  # Accept lower confidence
"FALLBACK_TO_CLASSIC": True,   # Always fallback
```

## Output Format

Detected curves now include confidence information:

```python
curve_info = {
    'data': DataFrame,                  # Curve data
    'start_idx': 150,                   # Start index in original data
    'end_idx': 850,                     # End index in original data
    'duration': 58.3,                   # Duration in minutes
    'max_temp': 95.2,                   # Peak temperature (°C)
    'detection_method': 'fuzzy_logic',  # Detection method used
    'start_confidence': 0.92,           # Start detection confidence (0-1)
    'end_confidence': 0.98,             # End detection confidence (0-1)
    'contributing_factors': {
        'start': {
            'cold_rapid_oven': 0.87,        # Rule 1 contribution
            'warm_heating_oven': 0.72,      # Rule 2 contribution
            'ambient_oven_transition': 0.92 # Rule 7 contribution (winner)
        },
        'end': {
            'rapid_cooling': 0.98,          # Rule 1 contribution (winner)
            'large_temp_drop': 0.85,        # Rule 3 contribution
            'cooling_room_ambient': 0.65    # Rule 4 contribution
        }
    }
}
```

## Console Output

When loading a CSV file, you'll see detailed detection information:

```
🔍 Fuzzy Detection - Curve 1:
  Duration: 58.3 minutes
  Samples: 700
  Max temperature: 95.2°C
  Start confidence: 92.00%
  End confidence: 98.00%
  Start factors: ambient_oven_transition(92%), cold_rapid_oven(87%), warm_heating_oven(72%)
  End factors: rapid_cooling(98%), large_temp_drop(85%), cooling_room_ambient(65%)

✅ Fuzzy detection found 1 curve(s)
```

## Interpreting Confidence Scores

### Start Confidence:

- **90-100%**: Excellent - Clear oven entry signal
- **75-90%**: Good - Multiple indicators align
- **65-75%**: Acceptable - Some uncertainty but likely correct
- **<65%**: Questionable - May need manual review

### End Confidence:

- **95-100%**: Excellent - Clear probe removal or room temp plateau
- **80-95%**: Good - Strong cooling signal
- **65-80%**: Acceptable - Moderate cooling indication
- **<65%**: Questionable - Unclear end point

### Contributing Factors:

The top 3 factors show **which rules drove the detection**. This helps you understand:

1. **Why the curve was detected** - Which signals were strongest
2. **How reliable the detection is** - Are multiple factors in agreement?
3. **What to check if suspicious** - If only one factor is high, inspect that signal

## Edge Cases Handled

### 1. Pre-Inserted Probe (Cold Start)
**Scenario**: Probe inserted into dough before oven entry

**Classic method**: Triggers on insertion, misses oven entry
**Fuzzy method**: Uses ambient temperature to detect actual oven entry

```
Rule: IF ambient=oven AND gradient=heating THEN start (92% confidence)
```

### 2. Pre-Inserted Probe (Warm Start)
**Scenario**: Probe inserted into warm dough, then put in oven

**Classic method**: May miss gradual warmup
**Fuzzy method**: Detects sustained heating from beginning

```
Rule: IF temp=warm AND gradient=heating THEN start (85% confidence)
```

### 3. Partial Cooling Between Bakes
**Scenario**: Probe doesn't return to room temp between cycles

**Classic method**: May miss second bake start
**Fuzzy method**: Detects re-heating even from warm temperatures

```
Rule: IF gradient=heating AND ambient=oven THEN start (90% confidence)
```

### 4. Gradual Probe Removal
**Scenario**: Probe removed slowly, not rapid cooling

**Classic method**: May extend curve too long
**Fuzzy method**: Detects drop from peak + room temp approach

```
Rule: IF temp_drop>40 AND ambient=room THEN end (85% confidence)
```

### 5. Noisy Temperature Signals
**Scenario**: Sensor noise or environmental fluctuations

**Classic method**: May false-trigger on spikes
**Fuzzy method**: Uses stability analysis to filter noise

```
Rule: IF stability=volatile THEN reduce_confidence
```

## Testing

Test the fuzzy detector with your data:

```bash
# Activate virtual environment
source venv/bin/activate

# Run test script
python test_fuzzy_detection.py your_data.csv
```

The test script will:
1. Run fuzzy detection and show detailed results
2. Compare fuzzy vs classic detection methods
3. Display confidence scores and contributing factors

## Comparison: Classic vs Fuzzy

| Aspect | Classic Detection | Fuzzy Detection |
|--------|------------------|-----------------|
| **Thresholds** | Hard cutoffs | Soft boundaries |
| **Signals** | Sequential checking | Simultaneous evaluation |
| **Confidence** | Binary (yes/no) | Continuous (0-100%) |
| **Adaptability** | Fixed parameters | Self-tuning |
| **Explainability** | Limited | Full factor breakdown |
| **Edge Cases** | Struggles | Robust |
| **Speed** | Very fast | Fast |
| **Maintenance** | Manual tuning needed | Self-adapting |

## Troubleshooting

### Issue: No curves detected with fuzzy logic

**Solution 1**: Lower confidence threshold
```python
"CONFIDENCE_THRESHOLD": 0.55,  # From 0.65
```

**Solution 2**: Enable fallback to classic
```python
"FALLBACK_TO_CLASSIC": True,
```

**Solution 3**: Check console output for confidence scores
- If scores are 50-65%, try lowering threshold
- If scores are <50%, data may not have clear curves

### Issue: Too many curves detected

**Solution**: Raise confidence threshold
```python
"CONFIDENCE_THRESHOLD": 0.75,  # From 0.65
```

### Issue: Curve boundaries seem wrong

**Check**:
1. Review confidence scores - Low confidence = uncertain detection
2. Check contributing factors - Is detection based on weak signals?
3. Inspect temperature plots around boundaries
4. Consider using classic method for this specific case

### Issue: Fuzzy detection fails (falls back to classic)

**Causes**:
1. Missing temperature columns (no T1-T8)
2. All NaN values in temperature data
3. Very short dataset (<60 samples)
4. Exception in fuzzy logic code

**Solution**: Check console for error messages, verify CSV format

## Advanced: Customizing Fuzzy Logic

You can modify membership functions and rules in `src/data/fuzzy_curve_detector.py`:

### Adjust Temperature Ranges:
```python
# In FuzzyTemperatureClassifier.__init__()
self.cold = (temp_min, temp_min, 25)  # Change 25 to your threshold
self.warm = (35, 50, 70)               # Adjust triangle shape
```

### Adjust Gradient Sensitivity:
```python
# In FuzzyGradientClassifier.__init__()
self.rapid_heating = (12, 20, 40)  # Change sensitivity
```

### Add New Rules:
```python
# In FuzzyInferenceEngine.evaluate_start_rules()
rule8 = self.fuzzy_and(
    temp_class.get('hot', 0),
    grad_class.get('stable', 0)
)
factors['hot_stable'] = rule8 * 0.70  # Custom rule
```

### Change Rule Weights:
```python
# Increase confidence for specific rules
factors['cold_rapid_oven'] = rule1 * 0.98  # From 0.95
```

## References

1. **Fuzzy Logic Theory**: L.A. Zadeh, "Fuzzy Sets", Information and Control, 1965
2. **Fuzzy Inference Systems**: Mamdani & Assilian, "An Experiment in Linguistic Synthesis", 1975
3. **Industrial Applications**: J. Yen & R. Langari, "Fuzzy Logic: Intelligence, Control, and Information", 1999

## Future Enhancements

Planned improvements:
- [ ] Neural-fuzzy hybrid system (learning from user corrections)
- [ ] Multi-probe correlation (when using multiple probes)
- [ ] Time-series pattern recognition for curve classification
- [ ] Anomaly detection for quality control
- [ ] Automatic product type inference from curve shape
- [ ] Real-time confidence visualization in UI

## Support

For issues, questions, or suggestions about fuzzy detection:
1. Check console output for detailed diagnostic information
2. Review this guide for troubleshooting steps
3. Compare fuzzy vs classic results using test script
4. Report issues with confidence scores and contributing factors
