# Heating Consistency Calculation Bug Analysis & Fix Plan

## Bug Analysis

### Current Formula
```python
rate_consistency = 1 - (rates['core_rate'].std() / rates['core_rate'].mean())
```

### Root Cause
The formula fails when:
1. **Standard deviation > Mean**: Results in negative consistency (as seen: -0.0251)
2. **Mean ≈ 0**: During temperature plateaus, CV approaches infinity
3. **Mean < 0**: During cooling phases, the formula produces nonsensical results

### Example from Production Data
- Mean heating rate: 0.0436 °C/s
- Std deviation: 0.0447 °C/s
- CV: 1.0251 (std > mean)
- Result: -0.0251 consistency (impossible!)

## Recommended Fix

### Option 1: Normalized Range Approach (RECOMMENDED)
```python
def calculate_heating_consistency(self, rates: pd.Series) -> float:
    """
    Calculate heating rate consistency normalized to expected range.
    
    Returns a value between 0 (inconsistent) and 1 (perfectly consistent).
    """
    # Expected maximum heating rate for bread (°C/s)
    EXPECTED_MAX_RATE = 0.1  # 6°C/min is reasonable for bread
    
    # Calculate normalized standard deviation
    normalized_std = rates.std() / EXPECTED_MAX_RATE
    
    # Ensure result is between 0 and 1
    consistency = 1 - min(normalized_std, 1.0)
    
    return max(0, consistency)  # Ensure non-negative
```

### Option 2: Positive-Only Rates
```python
def calculate_heating_consistency(self, rates: pd.Series) -> float:
    """
    Calculate consistency using only positive (heating) rates.
    """
    # Filter for actual heating (ignore cooling/plateau)
    heating_rates = rates[rates > 0.01]  # Threshold for "actual heating"
    
    if len(heating_rates) < 10:  # Not enough heating data
        return 0.0
    
    # Use robust statistics (median/IQR instead of mean/std)
    q1 = heating_rates.quantile(0.25)
    q3 = heating_rates.quantile(0.75)
    iqr = q3 - q1
    median = heating_rates.median()
    
    # Calculate consistency based on IQR/median ratio
    if median > 0:
        consistency = 1 - min(iqr / (2 * median), 1.0)
    else:
        consistency = 0.0
    
    return max(0, consistency)
```

### Option 3: Smoothness-Based Metric
```python
def calculate_heating_consistency(self, rates: pd.Series) -> float:
    """
    Calculate consistency based on rate smoothness (low variation).
    """
    # Calculate rolling standard deviation
    window_size = 5  # 25 seconds at 5s intervals
    rolling_std = rates.rolling(window=window_size, center=True).std()
    
    # Average variability
    avg_variability = rolling_std.mean()
    
    # Normalize to expected range
    EXPECTED_VARIABILITY = 0.02  # °C/s
    
    consistency = 1 - min(avg_variability / EXPECTED_VARIABILITY, 1.0)
    
    return max(0, consistency)
```

## Implementation Plan

1. **Immediate Fix** (High Priority):
   - Replace current calculation with Option 1 (normalized range)
   - Add input validation and bounds checking
   - Add unit tests for edge cases

2. **Testing**:
   - Test with normal heating profiles
   - Test with plateau phases (soaking)
   - Test with cooling phases
   - Test with rapid heating/cooling

3. **Documentation**:
   - Add docstring explaining the metric
   - Document expected ranges
   - Add interpretation guide

---

# Quality Metrics Descriptions

## Core Temperature Metrics

### 1. **Core Uniformity CV (Coefficient of Variation)**
**Purpose**: Measures temperature consistency across multiple core sensors  
**Range**: 0.0 (perfect uniformity) to >0.1 (poor uniformity)  
**Interpretation**:
- < 0.02: Excellent - very even heating
- 0.02-0.05: Good - acceptable for most products
- 0.05-0.10: Acceptable - may have quality variations
- > 0.10: Poor - expect inconsistent product quality

**Why it matters**: Uneven core temperatures lead to some parts being over/under-baked, affecting texture and shelf life.

### 2. **Heating Rate Consistency**
**Purpose**: Measures how steady the heating rate is throughout baking  
**Range**: 0.0 (erratic) to 1.0 (perfectly steady)  
**Interpretation**:
- > 0.9: Excellent - very stable oven conditions
- 0.7-0.9: Good - normal variation
- 0.5-0.7: Acceptable - some oven cycling evident
- < 0.5: Poor - unstable conditions, check equipment

**Why it matters**: Consistent heating ensures predictable results and optimal texture development.

### 3. **Maximum Core Temperature**
**Purpose**: Confirms product reached safe internal temperature  
**Target**: 93-98°C for most bread products  
**Interpretation**:
- < 90°C: Under-baked, food safety risk
- 90-93°C: Marginal, may be gummy
- 93-98°C: Optimal for most breads
- > 98°C: Risk of dry crumb

**Why it matters**: Ensures food safety and proper starch gelatinization.

### 4. **Time to Target Temperature**
**Purpose**: Measures baking efficiency  
**Target**: 80-90% of total bake time  
**Interpretation**:
- < 80%: Too fast - exterior may burn before interior is done
- 80-90%: Optimal - balanced baking
- > 90%: Too slow - excessive moisture loss, energy waste

**Why it matters**: Indicates if oven zones are properly balanced.

## Surface Temperature Metrics

### 5. **Surface-Core Gradient**
**Purpose**: Measures temperature difference between crust and crumb  
**Typical Range**: 10-50°C during active baking  
**Interpretation**:
- < 10°C: Insufficient crust formation
- 10-30°C: Normal for soft breads
- 30-50°C: Normal for crusty breads
- > 50°C: Risk of burnt crust with raw center

**Why it matters**: Controls crust thickness and color development.

## Process Quality Metrics

### 6. **Zone Coverage**
**Purpose**: Percentage of critical temperature zones achieved  
**Range**: 0-100%  
**Interpretation**:
- 100%: All biochemical transformations completed
- 85-99%: Normal, minor zones may be brief
- 70-85%: Some zones missed, quality impact likely
- < 70%: Major process issues

**Why it matters**: Each zone represents critical chemical changes (yeast kill, starch gelatinization, etc.).

### 7. **Quality Score**
**Purpose**: Composite metric combining all quality factors  
**Range**: 0-100  
**Current Calculation**:
- Starts at 100
- Deducts points for:
  - Poor uniformity (up to -30)
  - Inconsistent heating (up to -20)
  - Missing target temperature (-25)

**Note**: Current implementation too simplistic - needs weighting by product type and critical vs. non-critical factors.

## Recommendations for Metric Improvements

1. **Add Product-Specific Targets**: Different products need different metrics
2. **Weight by Criticality**: Food safety metrics should weight more than aesthetics
3. **Include Economic Factors**: Energy efficiency, yield, waste reduction
4. **Add Predictive Metrics**: Estimated shelf life, moisture content, texture scores
5. **Statistical Process Control**: Cpk values, control limits, trend analysis